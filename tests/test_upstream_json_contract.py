"""Upstream attestation JSON must not accept ambiguous duplicate fields."""
import pytest

from app.reused.upstream import parse_unique_json


def test_valid_upstream_json_preserves_attestation_fields():
    assert parse_unique_json(b'{"tenant_id":"tenant-a","items":[]}') == {
        "tenant_id": "tenant-a", "items": []
    }


@pytest.mark.parametrize("payload", [
    b'{"tenant_id":"tenant-a","tenant_id":"tenant-b"}',
    b'{"id":1,"entities_id":2,"entities_id":3,"type":1}',
    b'{"nested":{"tenant_id":"a","tenant_id":"b"}}',
    b'{"items":[{"id":1,"id":2}]}',
])
def test_duplicate_keys_at_any_depth_rejected(payload):
    with pytest.raises(ValueError, match="duplicate"):
        parse_unique_json(payload)


@pytest.mark.parametrize("payload", [
    b'{"status":NaN}', b'{"status":Infinity}',
    b'{"status":-Infinity}',
])
def test_nonfinite_json_constants_rejected(payload):
    with pytest.raises(ValueError, match="non-finite"):
        parse_unique_json(payload)
