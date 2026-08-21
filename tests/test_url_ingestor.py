import unittest
from unittest.mock import patch

from app.services.url_ingestor import IngestionError, validate_public_http_url


class UrlIngestorSecurityTests(unittest.TestCase):
    def test_rejects_localhost(self):
        with self.assertRaises(IngestionError):
            validate_public_http_url("http://localhost:8000/article")

    def test_rejects_private_ipv4(self):
        with self.assertRaises(IngestionError):
            validate_public_http_url("http://192.168.1.10/article")

    def test_rejects_loopback_ipv4(self):
        with self.assertRaises(IngestionError):
            validate_public_http_url("http://127.0.0.1/article")

    def test_rejects_link_local_cloud_metadata(self):
        with self.assertRaises(IngestionError):
            validate_public_http_url("http://169.254.169.254/latest/meta-data/")

    def test_rejects_non_http_scheme(self):
        with self.assertRaises(IngestionError):
            validate_public_http_url("file:///etc/passwd")

    def test_rejects_hostname_resolving_private(self):
        fake_answer = [(2, 1, 6, "", ("10.0.0.8", 443))]
        with patch("app.services.url_ingestor.socket.getaddrinfo", return_value=fake_answer):
            with self.assertRaises(IngestionError):
                validate_public_http_url("https://news.example/article")

    def test_accepts_hostname_resolving_public(self):
        fake_answer = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with patch("app.services.url_ingestor.socket.getaddrinfo", return_value=fake_answer):
            validate_public_http_url("https://example.com/article")


if __name__ == "__main__":
    unittest.main()
