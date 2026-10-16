import re
import sys
import time

import pytest
from ckan.tests import factories

from ckanext.serverterminal import commands


COMMANDS_URL = "/admin/server-terminal/commands"
RUNS_URL = "/admin/server-terminal/runs"
SERVICES_URL = "/admin/server-terminal/services"


def _auth_headers(user):
    return {"Authorization": user["token"]}


@pytest.fixture
def fake_runs(tmp_path, ckan_config, monkeypatch):
    """Store runs in a temp folder and replace the real commands by a harmless one."""
    monkeypatch.setitem(ckan_config, commands.RUNS_DIR_KEY, str(tmp_path))
    started = []

    def fake_start_run(kind, display, argv, user):
        started.append({"kind": kind, "display": display, "argv": argv, "user": user})
        return {"id": "run-1", "kind": kind, "command": display, "user": user, "status": "running"}

    monkeypatch.setattr(commands, "start_run", fake_start_run)
    return started


@pytest.mark.parametrize("method, url", [
    ("post", COMMANDS_URL),
    ("post", "/admin/server-terminal/services/ckan/restart"),
    ("get", RUNS_URL),
    ("get", SERVICES_URL),
])
def test_regular_user_gets_403(app, method, url):
    user = factories.UserWithToken()

    getattr(app, method)(url, headers=_auth_headers(user), status=403)


def test_sysadmin_runs_allowed_command(app, fake_runs):
    sysadmin = factories.SysadminWithToken()

    response = app.post(
        COMMANDS_URL, json={"command": "search-index rebuild"},
        headers=_auth_headers(sysadmin), status=202,
    )

    assert response.json["command"] == "ckan search-index rebuild"
    assert fake_runs[0]["user"] == sysadmin["name"]
    assert fake_runs[0]["argv"][1] == "-c"
    assert fake_runs[0]["argv"][-2:] == ["search-index", "rebuild"]


@pytest.mark.parametrize("command", ["shell", "search-index rebuild && rm -rf /", ""])
def test_sysadmin_cannot_run_other_commands(app, fake_runs, command):
    sysadmin = factories.SysadminWithToken()

    response = app.post(
        COMMANDS_URL, json={"command": command},
        headers=_auth_headers(sysadmin), status=400,
    )

    assert response.json["error"]
    assert fake_runs == []


def test_only_one_ckan_command_at_a_time(app, fake_runs, monkeypatch):
    sysadmin = factories.SysadminWithToken()
    monkeypatch.setattr(commands, "ckan_command_running", lambda: True)

    app.post(
        COMMANDS_URL, json={"command": "jobs list"},
        headers=_auth_headers(sysadmin), status=409,
    )
    assert fake_runs == []


@pytest.mark.ckan_config(commands.SERVICES_KEY, "ckan ckan-worker")
def test_sysadmin_restarts_allowed_service(app, fake_runs):
    sysadmin = factories.SysadminWithToken()

    app.post(
        "/admin/server-terminal/services/ckan-worker/restart",
        headers=_auth_headers(sysadmin), status=202,
    )

    assert fake_runs[0]["kind"] == "service"
    assert fake_runs[0]["argv"][-2:] == ["restart", "ckan-worker"]


@pytest.mark.ckan_config(commands.SERVICES_KEY, "ckan ckan-worker")
def test_sysadmin_cannot_restart_other_services(app, fake_runs):
    sysadmin = factories.SysadminWithToken()

    app.post(
        "/admin/server-terminal/services/postgresql/restart",
        headers=_auth_headers(sysadmin), status=400,
    )
    assert fake_runs == []


def test_post_without_csrf_token_is_rejected(app, fake_runs):
    # Logged in with a session (not an API token): the CSRF token is required
    sysadmin = factories.Sysadmin()

    app.post(
        COMMANDS_URL, json={"command": "jobs list"},
        extra_environ={"REMOTE_USER": sysadmin["name"]}, status=400,
    )
    assert fake_runs == []


def test_post_with_csrf_token_from_the_page_is_accepted(app, fake_runs):
    # Same flow as the browser: read the token from the page and send it as a header
    # One client for both requests so the session cookie is kept, as in a browser
    sysadmin = factories.Sysadmin()
    environ = {"REMOTE_USER": sysadmin["name"]}
    client = app.test_client()
    page = client.get("/admin/server-terminal", extra_environ=environ).get_data(as_text=True)
    token = re.search(r'<meta name="_csrf_token" content="([^"]+)"', page).group(1)

    client.post(
        COMMANDS_URL, json={"command": "jobs list"},
        headers={"X-CSRFToken": token}, extra_environ=environ, status=202,
    )
    assert fake_runs[0]["argv"][-2:] == ["jobs", "list"]


def test_run_detail_includes_output(app, tmp_path, ckan_config, monkeypatch):
    monkeypatch.setitem(ckan_config, commands.RUNS_DIR_KEY, str(tmp_path))
    sysadmin = factories.SysadminWithToken()
    run = commands.start_run("ckan", "ckan test", [sys.executable, "-c", "print('done')"], "admin")
    run_id = run["id"]

    for _ in range(100):
        response = app.get(f"{RUNS_URL}/{run_id}", headers=_auth_headers(sysadmin))
        if response.json["status"] != "running":
            break
        time.sleep(0.2)

    assert response.json["status"] == "success"
    assert response.json["output"] == "done"

    runs = app.get(RUNS_URL, headers=_auth_headers(sysadmin)).json["runs"]
    assert [r["id"] for r in runs] == [run_id]


def test_unknown_run_returns_404(app, tmp_path, ckan_config, monkeypatch):
    monkeypatch.setitem(ckan_config, commands.RUNS_DIR_KEY, str(tmp_path))
    sysadmin = factories.SysadminWithToken()

    app.get(f"{RUNS_URL}/does-not-exist", headers=_auth_headers(sysadmin), status=404)


def test_terminal_page_shows_the_sections(app):
    sysadmin = factories.SysadminWithToken()

    page = app.get("/admin/server-terminal", headers=_auth_headers(sysadmin)).text

    assert 'id="server-terminal-logs"' in page
    assert 'id="server-terminal-commands"' in page
    assert 'id="server-terminal-history"' in page
    assert "search-index rebuild" in page
    # Services are only shown when configured
    assert 'id="server-terminal-services"' not in page


@pytest.mark.ckan_config(commands.SERVICES_KEY, "ckan ckan-worker")
def test_terminal_page_shows_configured_services(app):
    sysadmin = factories.SysadminWithToken()

    page = app.get("/admin/server-terminal", headers=_auth_headers(sysadmin)).text

    assert 'id="server-terminal-services"' in page
    assert 'data-terminal-service="ckan-worker"' in page


def test_restart_is_rejected_when_no_services_are_configured(app, fake_runs):
    sysadmin = factories.SysadminWithToken()

    app.post(
        "/admin/server-terminal/services/ckan/restart",
        headers=_auth_headers(sysadmin), status=400,
    )
    assert fake_runs == []
