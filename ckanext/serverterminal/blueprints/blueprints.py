"""Admin-only server tools: log viewer, CKAN commands and services."""

from __future__ import annotations

import logging
import platform
import shutil

from flask import Blueprint, jsonify, request
from flask_wtf.csrf import CSRFError, validate_csrf

import ckan.plugins.toolkit as toolkit

from ckanext.serverterminal import commands, log_reader


log = logging.getLogger(__name__)

serverterminal = Blueprint(
    "serverterminal", __name__, url_prefix="/admin/server-terminal"
)


@serverterminal.before_request
def _require_sysadmin() -> None:
    try:
        toolkit.check_access("sysadmin", {"user": toolkit.current_user.name})
    except toolkit.NotAuthorized:
        toolkit.abort(403, toolkit._("Need to be system administrator to administer"))


@serverterminal.before_request
def _check_csrf() -> None:
    # CKAN exempts extension blueprints from CSRF, so it is checked here.
    # Requests authenticated with an API token do not need it, as in CKAN core.
    if request.method != "POST" or toolkit.g.get("login_via_auth_header"):
        return
    if not toolkit.config.get("WTF_CSRF_ENABLED", True):
        return
    field_name = toolkit.config.get("WTF_CSRF_FIELD_NAME", "_csrf_token")
    token = request.headers.get("X-CSRFToken") or request.form.get(field_name)
    try:
        validate_csrf(token)
    except (CSRFError, ValueError):
        toolkit.abort(400, toolkit._("The CSRF token is missing or invalid. Reload the page."))


def _system_info() -> dict:
    return {
        "hostname": platform.node(),
        "disk_free": shutil.disk_usage("/").free,
    }


def _error(message: str, status: int):
    return jsonify({"error": message}), status


@serverterminal.get("")
def index():
    sources = [
        {"id": source_id, "name": log_reader.source_label(path)}
        for source_id, path in log_reader.configured_sources().items()
    ]
    return toolkit.render(
        "admin/server_terminal.html",
        extra_vars={
            "sources": sources,
            "system_info": _system_info(),
            "ckan_commands": [" ".join(entry) for entry in commands.allowed_ckan_commands()],
            "services": [
                {"name": name, "description": commands.service_description(name)}
                for name in commands.allowed_services()
            ],
        },
    )


@serverterminal.get("/logs")
def logs():
    try:
        source_id, path = log_reader.select_source(request.args.get("source"))
        content = log_reader.read_tail(path, request.args.get("lines", 500))
        stat = path.stat()
    except FileNotFoundError as error:
        return _error(str(error), 404)
    except (OSError, ValueError) as error:
        return _error(str(error), 400)

    return jsonify(
        {
            "source": source_id,
            "content": content,
            "size": stat.st_size,
            "modified": int(stat.st_mtime),
        }
    )


@serverterminal.post("/commands")
def run_ckan_command():
    text = (request.get_json(silent=True) or {}).get("command") or request.form.get("command", "")
    try:
        args = commands.parse_ckan_args(text)
    except commands.CommandError as error:
        return _error(str(error), 400)
    if commands.ckan_command_running():
        return _error(toolkit._("Another CKAN command is still running. Wait until it finishes."), 409)

    display = "ckan " + " ".join(args)
    user = toolkit.current_user.name
    log.warning("serverterminal: user %s runs '%s'", user, display)
    run = commands.start_run("ckan", display, commands.ckan_argv(args), user)
    return jsonify(run), 202


@serverterminal.get("/services")
def services():
    return jsonify({"services": commands.services_status()})


@serverterminal.post("/services/<name>/restart")
def restart_service(name: str):
    try:
        commands.validate_service(name)
    except commands.CommandError as error:
        return _error(str(error), 400)

    display = f"supervisorctl restart {name}"
    user = toolkit.current_user.name
    log.warning("serverterminal: user %s runs '%s'", user, display)
    run = commands.start_run("service", display, commands.supervisorctl_argv("restart", name), user)
    return jsonify(run), 202


@serverterminal.get("/runs")
def runs():
    return jsonify({"runs": commands.list_runs()})


@serverterminal.get("/runs/<run_id>")
def run_detail(run_id: str):
    try:
        run = commands.get_run(run_id)
        output = log_reader.read_tail(commands.run_output_path(run_id), log_reader.MAX_LINES)
    except commands.CommandError as error:
        return _error(str(error), 404)
    except OSError:
        output = ""
    run["output"] = output
    return jsonify(run)


def get_blueprints():
    return [serverterminal]
