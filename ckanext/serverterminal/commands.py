"""Predefined server commands: allowlisted CKAN CLI subcommands and supervisor services.

Commands never go through a shell: the argument list is passed as is to the
process. Each execution ("run") is started detached through
``ckanext.serverterminal.runner`` and stored in its own folder, so it survives
a restart of the CKAN web server and its output can be read later.
"""

from __future__ import annotations

import json
import os
import platform
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import ckan.plugins.toolkit as toolkit
from ckan.plugins.toolkit import _

from ckanext.serverterminal.log_reader import N_


CKAN_COMMANDS_KEY = "ckanext.serverterminal.ckan_commands"
SERVICES_KEY = "ckanext.serverterminal.services"
TIMEOUT_KEY = "ckanext.serverterminal.command_timeout"
RUNS_DIR_KEY = "ckanext.serverterminal.runs_dir"
SUPERVISOR_CONFIG_KEY = "ckanext.serverterminal.supervisor_config"

# Maintenance and read-only subcommands of CKAN core, available in any instance.
# Commands of other extensions (xloader, tracking, ...) are added per instance
# with CKAN_COMMANDS_KEY. Anything that opens a Python shell, edits the config,
# writes files, drops data or never ends is left out. Each entry also allows
# every option of that subcommand, so check them before adding one
# (e.g. "db pending-migrations" is not here because of --apply).
DEFAULT_CKAN_COMMANDS = ", ".join([
    "search-index check",
    "search-index list-orphans",
    "search-index list-unindexed",
    "search-index clear-orphans",
    "search-index rebuild",
    "search-index show",
    "jobs list",
    "jobs show",
    "jobs cancel",
    "jobs test",
    "sysadmin list",
    "db version",
    "plugin-info",
])
# Supervisor program names depend on each deployment: none by default
DEFAULT_SERVICES = ""
DEFAULT_TIMEOUT = 1800
DEFAULT_SUPERVISOR_CONFIG = "/etc/supervisor/supervisord.conf"
HELP_FLAGS = ("--help", "-h")
SHELL_CHARS = set(";&|<>$`\\\n\r")
MAX_RUNS_KEPT = 50

SERVICE_DESCRIPTIONS = {
    "ckan": N_("CKAN web server"),
    "ckan-worker": N_("Background jobs worker"),
    "yacron": N_("Scheduled tasks (yacron)"),
}


class CommandError(ValueError):
    """The requested command is not valid or not allowed."""


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def allowed_ckan_commands() -> list[tuple[str, ...]]:
    value = toolkit.config.get(CKAN_COMMANDS_KEY) or DEFAULT_CKAN_COMMANDS
    return [tuple(entry.split()) for entry in _split_list(value)]


def allowed_services() -> list[str]:
    value = toolkit.config.get(SERVICES_KEY) or DEFAULT_SERVICES
    return value.replace(",", " ").split()


def current_host() -> str:
    return platform.node()


def service_description(name: str) -> str:
    description = SERVICE_DESCRIPTIONS.get(name)
    return _(description) if description else ""


def parse_ckan_args(text: str) -> list[str]:
    """Split and validate what goes after ``ckan`` against the allowlist."""
    try:
        args = shlex.split(text or "")
    except ValueError:
        raise CommandError(_("The command could not be read. Check the quotes."))
    if not args:
        raise CommandError(_("Enter a CKAN subcommand."))
    # No shell is involved, so these would only be passed to ckan as plain text.
    # They are rejected anyway to make clear that commands cannot be chained.
    if any(char in text for char in SHELL_CHARS):
        raise CommandError(_("Shell operators such as ; & | > < $ ` are not allowed."))

    allowed = allowed_ckan_commands()
    for entry in allowed:
        if tuple(args[:len(entry)]) == entry:
            return args
    # "ckan jobs --help" is allowed when "jobs ..." has allowed subcommands
    if len(args) > 1 and args[-1] in HELP_FLAGS:
        prefix = tuple(args[:-1])
        if any(entry[:len(prefix)] == prefix for entry in allowed):
            return args
    raise CommandError(_("This subcommand is not in the list of allowed commands."))


def ckan_argv(args: list[str]) -> list[str]:
    ckan_bin = os.path.join(os.path.dirname(sys.executable), "ckan")
    config_file = toolkit.config.get("__file__") or os.environ.get("CKAN_INI", "")
    return [ckan_bin, "-c", config_file, *args]


def supervisorctl_argv(*args: str) -> list[str]:
    supervisorctl = shutil.which("supervisorctl") or "supervisorctl"
    config_file = toolkit.config.get(SUPERVISOR_CONFIG_KEY) or DEFAULT_SUPERVISOR_CONFIG
    return [supervisorctl, "-c", config_file, *args]


def validate_service(name: str) -> str:
    if name not in allowed_services():
        raise CommandError(_("This service is not in the list of allowed services."))
    return name


def services_status() -> list[dict]:
    """Return the supervisor status of each allowed service."""
    services = allowed_services()
    states = {}
    error = None
    try:
        result = subprocess.run(
            supervisorctl_argv("status", *services),
            capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL,
        )
        for line in result.stdout.splitlines():
            parts = line.split(None, 2)
            if len(parts) >= 2:
                states[parts[0]] = (parts[1], parts[2] if len(parts) > 2 else "")
    except (OSError, subprocess.SubprocessError) as exc:
        error = str(exc)

    status = []
    for name in services:
        state, details = states.get(name, ("UNKNOWN", error or ""))
        status.append({
            "name": name,
            "description": service_description(name),
            "state": state,
            "details": details,
        })
    return status


# Runs


def runs_dir() -> Path:
    configured = toolkit.config.get(RUNS_DIR_KEY)
    if configured:
        path = Path(configured)
    elif toolkit.config.get("ckan.storage_path"):
        path = Path(toolkit.config["ckan.storage_path"]) / "serverterminal" / "runs"
    else:
        path = Path(tempfile.gettempdir()) / "ckanext-serverterminal" / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_path(run_id: str) -> Path:
    # Run ids are generated here; reject anything else to avoid path tricks
    if not run_id or not all(c.isalnum() or c == "-" for c in run_id):
        raise CommandError(_("Unknown run."))
    path = runs_dir() / run_id
    if not path.is_dir():
        raise CommandError(_("Unknown run."))
    return path


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _run_info(path: Path) -> dict | None:
    meta = _read_json(path / "meta.json")
    if meta is None:
        return None
    result = _read_json(path / "result.json")
    if result is not None:
        meta.update(result)
        if result.get("timed_out"):
            meta["status"] = "timeout"
        else:
            meta["status"] = "success" if result.get("exit_code") == 0 else "failed"
    elif meta.get("host", current_host()) != current_host():
        # Started by another CKAN host: its process cannot be checked from here
        meta["status"] = "unknown"
    elif _pid_alive(meta.get("pid")):
        meta["status"] = "running"
    else:
        meta["status"] = "interrupted"
    meta.pop("argv", None)
    meta.pop("pid", None)
    return meta


def list_runs(limit: int = 20) -> list[dict]:
    runs = []
    for path in sorted(runs_dir().iterdir(), reverse=True):
        if path.is_dir():
            info = _run_info(path)
            if info:
                runs.append(info)
        if len(runs) >= limit:
            break
    return runs


def get_run(run_id: str) -> dict:
    info = _run_info(_run_path(run_id))
    if info is None:
        raise CommandError(_("Unknown run."))
    return info


def run_output_path(run_id: str) -> Path:
    return _run_path(run_id) / "output.log"


def ckan_command_running() -> bool:
    """Whether a CKAN command started on this host is still running."""
    return any(
        run["kind"] == "ckan" and run["status"] == "running" for run in list_runs()
    )


def _prune_runs() -> None:
    paths = sorted((p for p in runs_dir().iterdir() if p.is_dir()), reverse=True)
    for path in paths[MAX_RUNS_KEPT:]:
        shutil.rmtree(path, ignore_errors=True)


def start_run(kind: str, display: str, argv: list[str], user: str) -> dict:
    """Start ``argv`` detached and return the new run info."""
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    path = runs_dir() / run_id
    path.mkdir()
    try:
        timeout = int(toolkit.config.get(TIMEOUT_KEY) or DEFAULT_TIMEOUT)
    except ValueError:
        timeout = DEFAULT_TIMEOUT
    meta = {
        "id": run_id,
        "kind": kind,
        "command": display,
        "user": user,
        "host": current_host(),
        "started": int(time.time()),
        "timeout": timeout,
        "argv": argv,
    }
    (path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    process = subprocess.Popen(
        [sys.executable, "-m", "ckanext.serverterminal.runner", str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    meta["pid"] = process.pid
    (path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    _prune_runs()
    return get_run(run_id)
