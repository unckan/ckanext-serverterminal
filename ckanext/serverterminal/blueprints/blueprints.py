"""Admin-only server log viewer routes."""

from __future__ import annotations

import os
import platform
import shutil

from flask import Blueprint, jsonify, request

import ckan.plugins.toolkit as toolkit

from ckanext.serverterminal import log_reader


serverterminal = Blueprint(
    "serverterminal", __name__, url_prefix="/admin/server-terminal"
)


def _require_sysadmin() -> None:
    toolkit.check_access("sysadmin", {"user": toolkit.g.user})


def _system_info() -> dict:
    disk = shutil.disk_usage("/")
    try:
        with open("/proc/uptime", encoding="ascii") as uptime_file:
            uptime = int(float(uptime_file.read().split()[0]))
    except (OSError, ValueError):
        uptime = None

    return {
        "hostname": platform.node(),
        "python": platform.python_version(),
        "pid": os.getpid(),
        "uptime_seconds": uptime,
        "disk_total": disk.total,
        "disk_free": disk.free,
    }


@serverterminal.get("")
def index():
    _require_sysadmin()
    sources = [
        {"id": source_id, "name": path.name}
        for source_id, path in log_reader.configured_sources().items()
    ]
    return toolkit.render(
        "admin/server_terminal.html",
        extra_vars={"sources": sources, "system_info": _system_info()},
    )


@serverterminal.get("/logs")
def logs():
    _require_sysadmin()
    try:
        source_id, path = log_reader.select_source(request.args.get("source"))
        content = log_reader.read_tail(path, request.args.get("lines", 500))
        stat = path.stat()
    except FileNotFoundError as error:
        return jsonify({"error": str(error)}), 404
    except (OSError, ValueError) as error:
        return jsonify({"error": str(error)}), 400

    return jsonify(
        {
            "source": source_id,
            "content": content,
            "size": stat.st_size,
            "modified": int(stat.st_mtime),
        }
    )


def get_blueprints():
    return [serverterminal]
