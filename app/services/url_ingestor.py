import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


class IngestionError(ValueError):
    pass


@dataclass
class IngestedArticle:
    requested_url: str
    final_url: str
    title: str | None
    source_name: str | None
    text: str
    content_sha256: str
    content_type: str


def _is_public_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise IngestionError("Only http and https URLs are supported.")
    if not parsed.hostname:
        raise IngestionError("URL must include a hostname.")
    if parsed.username or parsed.password:
        raise IngestionError("URLs containing credentials are not allowed.")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise IngestionError("Local network URLs are not allowed.")

    try:
        literal = ipaddress.ip_address(hostname)
        if not _is_public_ip(str(literal)):
            raise IngestionError("Private or local network addresses are not allowed.")
        return
    except ValueError:
        pass

    try:
        answers = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise IngestionError("The hostname could not be resolved.") from exc

    resolved = {answer[4][0] for answer in answers}
    if not resolved or any(not _is_public_ip(address) for address in resolved):
        raise IngestionError("The hostname resolves to a private or restricted network address.")


def _extract_article_text(html: str) -> tuple[str | None, str | None, str]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer", "aside"]):
        tag.decompose()

    title = None
    if soup.title and soup.title.string:
        title = " ".join(soup.title.string.split())

    source_name = None
    for attrs in (
        {"property": "og:site_name"},
        {"name": "application-name"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            source_name = " ".join(tag["content"].split())
            break

    root = soup.find("article") or soup.find("main") or soup.body or soup
    blocks: list[str] = []
    for element in root.find_all(["p", "h1", "h2", "h3", "li"]):
        text = " ".join(element.get_text(" ", strip=True).split())
        if len(text) >= 40:
            blocks.append(text)

    text = "\n\n".join(blocks)
    if len(text) < 200:
        text = " ".join(root.get_text(" ", strip=True).split())

    if len(text) < 200:
        raise IngestionError("The page did not contain enough readable article text.")

    return title, source_name, text[:100_000]


def ingest_article_url(url: str, *, timeout_seconds: float = 12.0, max_redirects: int = 5) -> IngestedArticle:
    requested_url = url.strip()
    validate_public_http_url(requested_url)

    headers = {
        "User-Agent": "AmericanIdeaEvidence/0.4 (+https://oluwafemidiakhoa.github.io/American_Idea/)",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
    }

    current_url = requested_url
    with httpx.Client(timeout=timeout_seconds, headers=headers, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            validate_public_http_url(current_url)
            try:
                response = client.get(current_url)
            except httpx.RequestError as exc:
                raise IngestionError("The article URL could not be fetched.") from exc

            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise IngestionError("The source returned an invalid redirect.")
                current_url = urljoin(current_url, location)
                continue

            if response.status_code >= 400:
                raise IngestionError(f"The source returned HTTP {response.status_code}.")

            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise IngestionError("The URL does not appear to be an HTML article.")

            if len(response.content) > 5_000_000:
                raise IngestionError("The page is larger than the ingestion limit.")

            title, source_name, text = _extract_article_text(response.text)
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            return IngestedArticle(
                requested_url=requested_url,
                final_url=str(response.url),
                title=title,
                source_name=source_name,
                text=text,
                content_sha256=digest,
                content_type=content_type,
            )

    raise IngestionError("The article redirected too many times.")
