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


def test_exact_size_limit_preserves_benign_text():
    from app.reused.redaction import MAX_TEXT
    text = "x" * MAX_TEXT
    assert redact_text(text) == text


def test_multiple_secrets_in_same_diagnostic_are_all_redacted():
    text = "api_key=abcdefgh1234 secret:topsecret999 password=hunter123456"
    result = redact_text(text)
    assert "abcdefgh1234" not in result
    assert "topsecret999" not in result
    assert "hunter123456" not in result
    assert result.count("[REDACTED]") == 3


def test_case_insensitive_bearer_and_access_token_redaction():
    result = redact_text("bEaReR abcdefghijklmnop ACCESS_TOKEN=abcdefgh123456")
    assert "abcdefghijklmnop" not in result
    assert "abcdefgh123456" not in result


def test_repeated_redaction_does_not_reveal_secrets():
    original = "password=secret123456 and ghu_ABCDEF123456789"
    once = redact_text(original)
    twice = redact_text(once)
    assert "secret123456" not in twice
    assert "ghu_ABCDEF123456789" not in twice


def test_json_and_single_quoted_secret_fields_are_redacted():
    examples = [
        ('{"password": "secret123456"}', "secret123456"),
        ("{'api_key': 'abcdefghi123'}", "abcdefghi123"),
        ('password="secret123456"', "secret123456"),
    ]
    for diagnostic, secret in examples:
        result = redact_text(diagnostic)
        assert secret not in result
        assert "[REDACTED]" in result


def test_short_named_credentials_are_never_exposed():
    examples = [
        ("password=abc", "abc"),
        ('{"api_key":"xyz"}', "xyz"),
        ("secret:q", "q"),
        ("access_token=12345", "12345"),
    ]
    for diagnostic, secret in examples:
        result = redact_text(diagnostic)
        assert secret not in result, diagnostic
        assert "[REDACTED]" in result, diagnostic


def test_ambiguous_empty_credential_fails_closed():
    # Whitespace after a named credential is ambiguous; prefer over-redaction.
    result = redact_text("password= status=ok")
    assert "status=ok" not in result
    assert "[REDACTED]" in result


def test_common_prefixed_credentials_are_redacted():
    examples = [
        ("client_secret=clientSecret123", "clientSecret123"),
        ('{"refresh_token":"refreshToken123"}', "refreshToken123"),
        ("db_password=dbPassword123", "dbPassword123"),
        ("client-secret=hyphenSecret123", "hyphenSecret123"),
        ("refresh-token=hyphenToken123", "hyphenToken123"),
    ]
    for diagnostic, secret in examples:
        result = redact_text(diagnostic)
        assert secret not in result, diagnostic
        assert "[REDACTED]" in result, diagnostic
