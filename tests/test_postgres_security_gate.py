"""Static drift guards for Compose and Helm PostgreSQL security gates."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_GATE = ROOT / "postgres" / "preflight" / "02-schema-security.sql"
HELM_GATE = ROOT / "deploy" / "helm" / "gamma" / "preflight" / "02-schema-security.sql"

REPLAY_CONTRACT = (
    "Replay 0009 privilege-boundary audit",
    "gamma_replay_executor",
    "gamma_replay_maintenance",
    "replay_maintenance.purge_expired(integer,integer)",
    "search_path=pg_catalog, pg_temp",
    "Invalid replay cleanup policy",
    "replay_immutable_update",
    "replay_expiry_delete",
    "unexpected cleanup EXECUTE grantee",
)

def assert_replay_gate_contract(sql: str) -> None:
    missing = [marker for marker in REPLAY_CONTRACT if marker not in sql]
    if missing:
        raise AssertionError(f"Replay gate contract drift: {missing}")

def test_compose_and_helm_security_gates_are_byte_identical():
    compose = COMPOSE_GATE.read_bytes()
    helm = HELM_GATE.read_bytes()
    assert compose == helm, "Compose and Helm PostgreSQL gate scripts diverged"
    assert_replay_gate_contract(compose.decode("utf-8"))

def test_negative_gate_drift_cases_are_rejected():
    source = COMPOSE_GATE.read_text(encoding="utf-8")
    assert_replay_gate_contract(source)
    for marker in REPLAY_CONTRACT:
        mutated = source.replace(marker, "REMOVED_GATE_ASSERTION", 1)
        try:
            assert_replay_gate_contract(mutated)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"Gate drift was not detected after removing {marker!r}")
