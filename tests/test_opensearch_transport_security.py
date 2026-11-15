"""P2: prevent credential leakage and unverified remote OpenSearch connections."""
import pytest

from app.opensearch_adapter import validate_opensearch_transport
from app.settings import settings


@pytest.mark.parametrize("endpoint", [
    "http://search.internal:9200",
    "http://192.0.2.10:9200",
    "https://user:password@search.internal:9200",
    "https://search.internal:9200/?token=secret",
    "https://search.internal:9200/#fragment",
    "ftp://search.internal:9200",
    "https://search.internal:9200/other-path",
])
def test_unsafe_remote_endpoints_rejected(monkeypatch, endpoint):
    monkeypatch.setattr(settings, "opensearch_url", endpoint)
    monkeypatch.setattr(settings, "opensearch_username", "")
    monkeypatch.setattr(settings, "opensearch_password", "")
    monkeypatch.setattr(settings, "opensearch_verify_certs", True)
    with pytest.raises(ValueError, match="OpenSearch"):
        validate_opensearch_transport()


def test_local_http_without_credentials_is_allowed_for_development(monkeypatch):
    monkeypatch.setattr(settings, "opensearch_url", "http://127.0.0.1:9200")
    monkeypatch.setattr(settings, "opensearch_username", "")
    monkeypatch.setattr(settings, "opensearch_password", "")
    validate_opensearch_transport()


def test_local_http_with_credentials_rejected(monkeypatch):
    monkeypatch.setattr(settings, "opensearch_url", "http://localhost:9200")
    monkeypatch.setattr(settings, "opensearch_username", "reader")
    with pytest.raises(ValueError, match="TLS"):
        validate_opensearch_transport()


def test_remote_https_with_verified_certificates_allowed(monkeypatch):
    monkeypatch.setattr(settings, "opensearch_url", "https://search.internal:9200")
    monkeypatch.setattr(settings, "opensearch_username", "reader")
    monkeypatch.setattr(settings, "opensearch_password", "secret")
    monkeypatch.setattr(settings, "opensearch_verify_certs", True)
    validate_opensearch_transport()


def test_disabling_https_certificate_verification_rejected(monkeypatch):
    monkeypatch.setattr(settings, "opensearch_url", "https://search.internal:9200")
    monkeypatch.setattr(settings, "opensearch_verify_certs", False)
    with pytest.raises(ValueError, match="certificate verification"):
        validate_opensearch_transport()
