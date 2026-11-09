from app.reused.redaction import redact_text


def test_github_token_and_jwt_hidden():
    text = "token=ghs_ABCDEF123456789 hello eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.sig"
    result = redact_text(text)
    assert "ghs_ABCDEF" not in result
    assert "eyJhbGciOiJSUzI1NiJ9" not in result


def test_bearer_and_password_hidden():
    result = redact_text("Bearer abcdefghijklmnopqrstuvwxyz password=secret123456")
    assert "abcdefghijklmnopqrstuvwxyz" not in result
    assert "secret123456" not in result


def test_oversize_redaction_fail_closed():
    assert redact_text("x"*100001) == "[REDACTED:OVERSIZE]"


def test_idempotent_and_none():
    assert redact_text(redact_text("password=verySecret123")) == "password=[REDACTED]"
    assert redact_text(None) is None
