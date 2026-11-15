"""P1 CMDB/OTel binding identity validation before tenant-scoped writes."""
import pytest
from pydantic import ValidationError

from app.schemas import BindingIn


CMDB_ID = "11111111-1111-4111-8111-111111111111"


def binding(**changes):
    values = {
        "cmdb_service_id": CMDB_ID,
        "otel_service_name": "checkout.api",
        "environment": "production",
    }
    values.update(changes)
    return BindingIn(**values)


@pytest.mark.parametrize("field", ["otel_service_name", "environment"])
@pytest.mark.parametrize("bad", ["", " leading", "trailing ", "line\nfeed", "null\x00byte", "del\x7f"])
def test_binding_identity_rejects_noncanonical_values(field, bad):
    with pytest.raises(ValidationError):
        binding(**{field: bad})


@pytest.mark.parametrize("field,max_length", [
    ("otel_service_name", 255), ("environment", 100),
])
def test_binding_identity_length_boundaries(field, max_length):
    assert getattr(binding(**{field: "x" * max_length}), field) == "x" * max_length
    with pytest.raises(ValidationError):
        binding(**{field: "x" * (max_length + 1)})


def test_valid_binding_preserves_identity():
    result = binding()
    assert result.otel_service_name == "checkout.api"
    assert result.environment == "production"
