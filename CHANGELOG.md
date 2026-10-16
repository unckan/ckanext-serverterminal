# Next release

 - Add CHANGELOG

# 0.1.0 2026-10-02

First release.

 - Read-only server log viewer for sysadmins at `/admin/server-terminal`, also listed as a tab in the admin panel
 - Logs restricted to an allowlist (`ckanext.serverterminal.log_paths`, default `/var/log/supervisor/*.log`)
 - Responses limited to 2000 lines and 512 KiB
 - Basic server info: hostname, PID, Python version and free disk space
 - Spanish translations
