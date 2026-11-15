"""P1/P2 defense-in-depth: reject untrusted cross-tenant OpenSearch results."""
import pytest

from app.opensearch_adapter import validate_log_search_response

TENANT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def hit(tenant=TENANT, service="checkout"):
    return {"_id": "log-1", "_source": {
        "tenant": {"id": tenant},
        "resource": {"attributes": {"service.name": service}},
        "body": "request failed",
    }}


def result(hits):
    return {"hits": {"hits": hits}}


def test_valid_scoped_log_is_returned():
    response = result([hit()])
    assert validate_log_search_response(response, TENANT, "checkout", 10) is response


def test_empty_result_is_allowed():
    assert validate_log_search_response(result([]), TENANT, "checkout", 10) == result([])


@pytest.mark.parametrize("document", [
    hit(tenant=OTHER),
    hit(service="billing"),
    {"_id": "log-1", "_source": {"body": "unscoped"}},
    {"_id": "log-1"},
    {"_id": "log-1", "_source": None},
])
def test_cross_scope_or_unverifiable_hit_is_rejected(document):
    with pytest.raises(ValueError, match="OpenSearch"):
        validate_log_search_response(result([document]), TENANT, "checkout", 10)


@pytest.mark.parametrize("response", [None, [], {}, {"hits": {}}, {"hits": {"hits": None}}])
def test_malformed_response_rejected(response):
    with pytest.raises(ValueError, match="Invalid OpenSearch response"):
        validate_log_search_response(response, TENANT, "checkout", 10)


def test_backend_cannot_return_more_hits_than_requested():
    with pytest.raises(ValueError, match="more hits"):
        validate_log_search_response(result([hit(), hit()]), TENANT, "checkout", 1)
