"""Source-only checks for the local Compose install path; no Docker or DB needed."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_api_image_contains_migration_sources():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY migrations ./migrations" in dockerfile
    assert "COPY alembic.ini ./alembic.ini" in dockerfile


def test_compose_migration_gate_is_explicit():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "  migrate:" in compose
    assert 'command: ["alembic", "upgrade", "head"]' in compose
    assert "condition: service_completed_successfully" in compose
    assert "condition: service_healthy" in compose


def test_local_smoke_is_read_only_and_loopback_bound():
    script = (ROOT / "scripts/smoke_local_mvp.py").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8000/api/v1/health/live" in script
    assert "http://127.0.0.1:5173/" in script
    assert "SELECT version_num FROM alembic_version" in script
    assert "docker\", \"compose\", \"exec\"" in script
    assert "docker compose down" not in script
