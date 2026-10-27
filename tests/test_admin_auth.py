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
