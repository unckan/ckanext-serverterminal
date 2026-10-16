import sys
import time

import pytest

from ckanext.serverterminal import commands


def _wait_for(run_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = commands.get_run(run_id)
        if run["status"] != "running":
            return run
        time.sleep(0.2)
    raise AssertionError("The run did not finish")


@pytest.fixture
def runs_dir(tmp_path, ckan_config, monkeypatch):
    monkeypatch.setitem(ckan_config, commands.RUNS_DIR_KEY, str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("text, expected", [
    ("search-index rebuild", ["search-index", "rebuild"]),
    ("search-index rebuild my-dataset", ["search-index", "rebuild", "my-dataset"]),
    ("jobs list --help", ["jobs", "list", "--help"]),
    ("jobs --help", ["jobs", "--help"]),
    ("plugin-info", ["plugin-info"]),
])
def test_allowed_ckan_commands(text, expected):
    assert commands.parse_ckan_args(text) == expected


@pytest.mark.parametrize("text", [
    "",
    "shell",
    "config-tool /app/ckan.ini debug=true",
    "db clean",
    "jobs worker",
    "search-index clear",
    "db pending-migrations --apply",
    "generate extension",
    "-c /tmp/other.ini search-index rebuild",
    "--help",
    "shell --help",
])
def test_not_allowed_ckan_commands(text):
    with pytest.raises(commands.CommandError):
        commands.parse_ckan_args(text)


@pytest.mark.parametrize("text", [
    "search-index rebuild && rm -rf /",
    "search-index rebuild; rm -rf /",
    "search-index rebuild | sh",
    "search-index rebuild > /tmp/out",
    "search-index rebuild $(id)",
    "search-index rebuild `id`",
    "search-index rebuild\nshell",
])
def test_shell_operators_are_rejected(text):
    with pytest.raises(commands.CommandError):
        commands.parse_ckan_args(text)


def test_unbalanced_quotes_are_rejected():
    with pytest.raises(commands.CommandError):
        commands.parse_ckan_args('search-index show "abc')


@pytest.mark.ckan_config(commands.CKAN_COMMANDS_KEY, "search-index check, jobs list")
def test_allowlist_is_configurable():
    assert commands.parse_ckan_args("jobs list") == ["jobs", "list"]
    with pytest.raises(commands.CommandError):
        commands.parse_ckan_args("search-index rebuild")


def test_ckan_argv_uses_instance_config():
    argv = commands.ckan_argv(["search-index", "check"])
    assert argv[0].endswith("ckan")
    assert argv[1] == "-c"
    assert argv[-2:] == ["search-index", "check"]


@pytest.mark.ckan_config(commands.SERVICES_KEY, "ckan ckan-worker")
def test_validate_service():
    assert commands.validate_service("ckan-worker") == "ckan-worker"
    with pytest.raises(commands.CommandError):
        commands.validate_service("postgresql")


@pytest.mark.ckan_config(commands.SERVICES_KEY, "ckan ckan-worker yacron")
def test_services_status_parses_supervisorctl(monkeypatch):
    output = (
        "ckan                             RUNNING   pid 393, uptime 0:14:52\n"
        "ckan-worker                      STOPPED   Oct 16 01:00 AM\n"
    )

    class Result:
        stdout = output

    monkeypatch.setattr(commands.subprocess, "run", lambda *args, **kwargs: Result())
    status = {service["name"]: service for service in commands.services_status()}

    assert status["ckan"]["state"] == "RUNNING"
    assert status["ckan"]["details"] == "pid 393, uptime 0:14:52"
    assert status["ckan-worker"]["state"] == "STOPPED"
    assert status["yacron"]["state"] == "UNKNOWN"


def test_run_records_output_and_exit_code(runs_dir):
    argv = [sys.executable, "-c", "print('hello'); raise SystemExit(3)"]
    run = commands.start_run("ckan", "ckan test", argv, "admin")

    run = _wait_for(run["id"])

    assert run["status"] == "failed"
    assert run["exit_code"] == 3
    assert run["user"] == "admin"
    assert run["command"] == "ckan test"
    assert "argv" not in run
    assert commands.run_output_path(run["id"]).read_text().strip() == "hello"
    assert [r["id"] for r in commands.list_runs()] == [run["id"]]


@pytest.mark.ckan_config(commands.TIMEOUT_KEY, "1")
def test_run_is_stopped_after_timeout(runs_dir):
    argv = [sys.executable, "-c", "import time; time.sleep(30)"]
    run = commands.start_run("ckan", "ckan slow", argv, "admin")

    run = _wait_for(run["id"])

    assert run["status"] == "timeout"


@pytest.mark.parametrize("run_id", ["../etc", "", "a/b", "nope"])
def test_unknown_run_ids_are_rejected(runs_dir, run_id):
    with pytest.raises(commands.CommandError):
        commands.get_run(run_id)


def test_runs_never_use_a_shell(runs_dir, tmp_path):
    # Shell syntax reaches the process as plain arguments: nothing is chained
    marker = tmp_path / "pwned"
    script = "import sys; print(sys.argv[1:])"
    argv = [sys.executable, "-c", script, "rebuild", "&&", "touch", str(marker), ";", "$(id)"]
    run = commands.start_run("ckan", "ckan test", argv, "admin")

    run = _wait_for(run["id"])

    output = commands.run_output_path(run["id"]).read_text()
    assert f"'rebuild', '&&', 'touch', '{marker}', ';', '$(id)'" in output
    assert not marker.exists()


def test_defaults_are_ckan_core_only():
    entries = [entry[0] for entry in commands.allowed_ckan_commands()]
    assert set(entries) == {"search-index", "jobs", "sysadmin", "db", "plugin-info"}
    assert commands.allowed_services() == []
    with pytest.raises(commands.CommandError):
        commands.parse_ckan_args("xloader status")


@pytest.mark.ckan_config(commands.CKAN_COMMANDS_KEY, "search-index rebuild, xloader status")
def test_extension_commands_can_be_added():
    assert commands.parse_ckan_args("xloader status") == ["xloader", "status"]


def test_run_from_another_host_is_unknown_and_does_not_block(runs_dir, monkeypatch):
    argv = [sys.executable, "-c", "import time; time.sleep(30)"]
    monkeypatch.setattr(commands, "current_host", lambda: "host-a")
    run = commands.start_run("ckan", "ckan slow", argv, "admin")
    assert commands.get_run(run["id"])["status"] == "running"
    assert commands.ckan_command_running()

    monkeypatch.setattr(commands, "current_host", lambda: "host-b")
    run = commands.get_run(run["id"])
    assert run["status"] == "unknown"
    assert run["host"] == "host-a"
    assert not commands.ckan_command_running()
