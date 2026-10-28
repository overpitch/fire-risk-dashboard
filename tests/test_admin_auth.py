import time
import pytest
from unittest.mock import patch

import admin_service
from admin_endpoints import admin_sessions, SESSION_DURATION

TEST_PASSWORD = "correct horse battery staple"

# Every route that changes state or exposes subscriber data must reject anonymous requests
PROTECTED_ROUTES = [
    ("get", "/admin/subscribers", {}),
    ("get", "/admin/test-mode-status", {}),
    ("post", "/admin/import-subscribers", {"files": {"file": ("subs.csv", b"email\na@example.com\n", "text/csv")}}),
    ("post", "/admin/test-email-alert", {"json": {"emails": ["a@example.com"]}}),
    ("post", "/admin/send-custom-email", {"json": {"subject": "s", "html_content": "<p>x</p>", "recipients": ["a@example.com"]}}),
    ("post", "/admin/test-conditions", {"json": {"temperature": 100}}),
    ("delete", "/admin/test-conditions", {}),
    ("post", "/admin/settings/email-limit", {"json": {"ignore_daily_limit": True}}),
    ("get", "/admin/settings/email-limit-status", {}),
    ("post", "/toggle-test-mode?enable=true", {}),
]


@pytest.fixture(autouse=True)
def admin_password():
    """Configure a known admin password and clear login lockouts for each test."""
    admin_service.failed_attempts.clear()
    with patch.object(admin_service, "ADMIN_PASSWORD", TEST_PASSWORD):
        yield
    admin_service.failed_attempts.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,kwargs", PROTECTED_ROUTES)
async def test_protected_routes_reject_anonymous(client, method, path, kwargs):
    with patch("admin_endpoints.bulk_import_subscribers") as mock_import, \
         patch("admin_endpoints.send_test_orange_to_red_alert") as mock_send:
        response = await getattr(client, method)(path, **kwargs)
    assert response.status_code == 401
    mock_import.assert_not_called()
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_toggle_test_mode_rejects_get(admin_client):
    response = await admin_client.get("/toggle-test-mode?enable=true")
    assert response.status_code == 405


@pytest.mark.asyncio
async def test_login_sets_httponly_session_cookie(client):
    response = await client.post("/admin/validate-password", json={"password": TEST_PASSWORD})
    assert response.status_code == 200
    assert response.json() == {"valid": True}  # token is not exposed to page scripts
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie

    # The cookie grants access to protected routes
    with patch("admin_endpoints.get_active_subscribers", return_value={"subscribers": []}):
        response = await client.get("/admin/subscribers")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(client):
    response = await client.post("/admin/validate-password", json={"password": "wrong"})
    assert response.json()["valid"] is False
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_form_login_sets_cookie_on_redirect(client):
    response = await client.post("/admin", data={"password": TEST_PASSWORD})
    assert response.status_code == 303
    assert "session_token=" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_login_disabled_without_configured_password(client):
    with patch.object(admin_service, "ADMIN_PASSWORD", None):
        response = await client.post("/admin/validate-password", json={"password": ""})
        assert response.status_code == 400
        response = await client.post("/admin/validate-password", json={"password": "anything"})
    assert response.json()["valid"] is False


@pytest.mark.asyncio
async def test_expired_session_is_rejected(client):
    token = "expired-session-token"
    admin_sessions[token] = {"ip": "test", "created_at": time.time() - SESSION_DURATION - 1}
    client.cookies.set("session_token", token)
    response = await client.get("/admin/settings/email-limit-status")
    assert response.status_code == 401
    assert token not in admin_sessions


@pytest.mark.asyncio
async def test_logout_ends_session(admin_client):
    response = await admin_client.get("/admin/logout")
    assert response.status_code == 303
    assert "test-admin-session-token" not in admin_sessions


@pytest.mark.asyncio
@pytest.mark.parametrize("age,expect_test_result", [(0, True), (SESSION_DURATION + 1, False)])
async def test_fire_risk_shows_test_result_only_for_unexpired_session(client, age, expect_test_result):
    """An expired admin session must not see (or apply) its old test conditions."""
    from cache import data_cache

    token = "override-session-token"
    admin_sessions[token] = {"ip": "test", "created_at": time.time() - age,
                             "manual_weather_overrides": {"temperature": 120.0},
                             "test_fire_risk_data": {"risk": "Red", "explanation": "test", "weather": {}}}
    client.cookies.set("session_token", token)
    original_data = data_cache.fire_risk_data
    data_cache.fire_risk_data = {"risk": "Green", "explanation": "live", "weather": {}}
    try:
        with patch.object(data_cache, "is_stale", return_value=False):
            response = await client.get("/fire-risk")
        assert response.json()["risk"] == ("Red" if expect_test_result else "Green")
    finally:
        data_cache.fire_risk_data = original_data
        admin_sessions.pop(token, None)


@pytest.mark.asyncio
async def test_form_login_failure_shows_server_message(client):
    response = await client.post("/admin", data={"password": "wrong"})
    assert "4 attempts remaining" in response.text


async def _login(client, password, forwarded_for=None):
    """forwarded_for: one X-Forwarded-For value, or a list of values sent as separate header lines."""
    values = [forwarded_for] if isinstance(forwarded_for, str) else (forwarded_for or [])
    headers = [("X-Forwarded-For", value) for value in values]
    response = await client.post("/admin/validate-password", json={"password": password}, headers=headers)
    return response.json()


async def _fail_until_locked(client, forwarded_for):
    for _ in range(admin_service.MAX_ATTEMPTS):
        await _login(client, "wrong", forwarded_for=forwarded_for)


def _is_locked(result):
    return result["valid"] is False and "Too many failed attempts" in result["error"]


@pytest.fixture
def behind_one_proxy():
    with patch("admin_endpoints.TRUSTED_PROXY_HOPS", 1):
        yield


@pytest.mark.asyncio
async def test_lockout_applies_per_visitor_not_to_everyone(client, behind_one_proxy):
    """Behind Render's proxy, one visitor's failed guesses must not lock out the admin."""
    await _fail_until_locked(client, "203.0.113.10")
    assert _is_locked(await _login(client, TEST_PASSWORD, forwarded_for="203.0.113.10"))
    assert (await _login(client, TEST_PASSWORD, forwarded_for="198.51.100.20"))["valid"] is True


@pytest.mark.asyncio
async def test_spoofed_forwarded_addresses_do_not_bypass_lockout(client, behind_one_proxy):
    """A visitor can prepend fake addresses, but the proxy-appended last address is what counts."""
    for i in range(admin_service.MAX_ATTEMPTS):
        await _login(client, "wrong", forwarded_for=f"10.0.0.{i}, 203.0.113.10")
    assert _is_locked(await _login(client, TEST_PASSWORD, forwarded_for="10.9.9.9, 203.0.113.10"))


@pytest.mark.asyncio
async def test_separate_spoofed_header_line_does_not_bypass_lockout(client, behind_one_proxy):
    for i in range(admin_service.MAX_ATTEMPTS):
        await _login(client, "wrong", forwarded_for=[f"10.0.0.{i}", "203.0.113.10"])
    assert _is_locked(await _login(client, TEST_PASSWORD, forwarded_for=["10.9.9.9", "203.0.113.10"]))


@pytest.mark.asyncio
async def test_blank_trailing_entry_is_ignored(client, behind_one_proxy):
    await _fail_until_locked(client, "203.0.113.10, ")
    assert _is_locked(await _login(client, TEST_PASSWORD, forwarded_for="203.0.113.10"))


@pytest.mark.asyncio
async def test_two_proxy_hops_uses_the_visitor_entry(client):
    with patch("admin_endpoints.TRUSTED_PROXY_HOPS", 2):
        await _fail_until_locked(client, "10.0.0.1, 203.0.113.10, 104.16.0.1")
        assert _is_locked(await _login(client, TEST_PASSWORD, forwarded_for="10.0.0.9, 203.0.113.10, 104.16.0.2"))
        assert (await _login(client, TEST_PASSWORD, forwarded_for="198.51.100.20, 104.16.0.1"))["valid"] is True


@pytest.mark.asyncio
async def test_header_ignored_without_trusted_proxy(client):
    """Outside Render (no trusted proxy) the header is ignored, so rotating it can't dodge the lockout."""
    with patch("admin_endpoints.TRUSTED_PROXY_HOPS", 0):
        for i in range(admin_service.MAX_ATTEMPTS):
            await _login(client, "wrong", forwarded_for=f"203.0.113.{i}")
        assert _is_locked(await _login(client, TEST_PASSWORD, forwarded_for="203.0.113.99"))


@pytest.mark.asyncio
async def test_lockout_records_are_cleaned_up(client, behind_one_proxy):
    await _login(client, "wrong", forwarded_for="203.0.113.10")
    await _login(client, TEST_PASSWORD, forwarded_for="203.0.113.10")
    assert "203.0.113.10" not in admin_service.failed_attempts  # success forgets the visitor

    admin_service.failed_attempts["198.51.100.1"] = {"attempts": [time.time() - admin_service.ATTEMPT_WINDOW - 1]}
    await _login(client, "wrong", forwarded_for="203.0.113.10")
    assert "198.51.100.1" not in admin_service.failed_attempts  # stale record pruned
