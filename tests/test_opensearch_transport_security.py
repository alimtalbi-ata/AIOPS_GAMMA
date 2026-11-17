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


@pytest.mark.parametrize("username,password", [
    ("reader", ""),
    ("", "secret"),
])
def test_partial_basic_auth_credentials_rejected(monkeypatch, username, password):
    monkeypatch.setattr(settings, "opensearch_url", "https://search.internal:9200")
    monkeypatch.setattr(settings, "opensearch_verify_certs", True)
    monkeypatch.setattr(settings, "opensearch_username", username)
    monkeypatch.setattr(settings, "opensearch_password", password)
    with pytest.raises(ValueError, match="configured together"):
        validate_opensearch_transport()


@pytest.mark.parametrize("endpoint", [
    " https://search.internal:9200",
    "https://search.internal:9200 ",
    "https://search.internal:9200\n",
])
def test_noncanonical_endpoint_whitespace_rejected(monkeypatch, endpoint):
    monkeypatch.setattr(settings, "opensearch_url", endpoint)
    monkeypatch.setattr(settings, "opensearch_username", "")
    monkeypatch.setattr(settings, "opensearch_password", "")
    monkeypatch.setattr(settings, "opensearch_verify_certs", True)
    with pytest.raises(ValueError, match="Invalid OpenSearch endpoint"):
        validate_opensearch_transport()


@pytest.mark.parametrize("index", [
    "*", "_all", "logs-*,other-*", "logs-*,-secret-*",
    ".internal-*", "logs-**", "logs-?", "logs-*\\n", "",
])
def test_unbounded_or_ambiguous_index_configuration_rejected(monkeypatch, index):
    monkeypatch.setattr(settings, "opensearch_url", "https://search.internal:9200")
    monkeypatch.setattr(settings, "opensearch_username", "")
    monkeypatch.setattr(settings, "opensearch_password", "")
    monkeypatch.setattr(settings, "opensearch_verify_certs", True)
    monkeypatch.setattr(settings, "opensearch_logs_index", index)
    with pytest.raises(ValueError, match="logs index"):
        validate_opensearch_transport()


@pytest.mark.parametrize("index", ["aiops-logs-v1-*", "aiops-logs-v1-2026.11"])
def test_bounded_index_configuration_allowed(monkeypatch, index):
    monkeypatch.setattr(settings, "opensearch_url", "https://search.internal:9200")
    monkeypatch.setattr(settings, "opensearch_username", "")
    monkeypatch.setattr(settings, "opensearch_password", "")
    monkeypatch.setattr(settings, "opensearch_verify_certs", True)
    monkeypatch.setattr(settings, "opensearch_logs_index", index)
    validate_opensearch_transport()
