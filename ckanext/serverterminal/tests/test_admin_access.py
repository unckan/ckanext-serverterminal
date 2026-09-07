import pytest
from ckan.plugins import toolkit
from ckan.tests import factories

from ckanext.serverterminal import log_reader


ADMIN_URL = "/ckan-admin/"
TERMINAL_URL = "/admin/server-terminal"
LOGS_URL = "/admin/server-terminal/logs"


def _auth_headers(user):
    return {"Authorization": user["token"]}


def test_regular_user_cannot_access_terminal_page(app):
    user = factories.UserWithToken()

    with pytest.raises(toolkit.NotAuthorized):
        app.get(TERMINAL_URL, headers=_auth_headers(user))


def test_regular_user_cannot_read_terminal_logs(app):
    user = factories.UserWithToken()

    with pytest.raises(toolkit.NotAuthorized):
        app.get(LOGS_URL, headers=_auth_headers(user))


def test_sysadmin_sees_terminal_tab_and_page(app):
    sysadmin = factories.SysadminWithToken()

    admin_page = app.get(ADMIN_URL, headers=_auth_headers(sysadmin))
    terminal_page = app.get(TERMINAL_URL, headers=_auth_headers(sysadmin))

    assert "Terminal del servidor" in admin_page.text
    assert TERMINAL_URL in admin_page.text
    assert "Terminal del servidor" in terminal_page.text


def test_sysadmin_can_read_allowlisted_logs(app, monkeypatch, tmp_path):
    sysadmin = factories.SysadminWithToken()
    log_file = tmp_path / "ckan.log"
    log_file.write_text("first line\nlast line\n", encoding="utf-8")
    monkeypatch.setattr(
        log_reader, "configured_sources", lambda: {"test-log": log_file}
    )

    response = app.get(
        f"{LOGS_URL}?source=test-log&lines=1",
        headers=_auth_headers(sysadmin),
    )

    assert response.json["source"] == "test-log"
    assert response.json["content"] == "last line"