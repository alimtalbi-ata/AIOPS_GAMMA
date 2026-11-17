"""P1: incident resource keys must be canonical and fit the database column."""
import pytest
from fastapi import HTTPException

from app.main import validate_incident_resource_id


@pytest.mark.parametrize("incident_id", [
    "incident-123", "INC_42", "x" * 255,
])
def test_valid_incident_resource_identifiers(incident_id):
    assert validate_incident_resource_id(incident_id) == incident_id


@pytest.mark.parametrize("incident_id", [
    "", " incident-123", "incident-123 ", "incident\n123",
    "incident\x00id", "incident\x7fid", "x" * 256,
])
def test_invalid_incident_resource_identifiers_fail_closed(incident_id):
    with pytest.raises(HTTPException) as exc:
        validate_incident_resource_id(incident_id)
    assert exc.value.status_code == 422
