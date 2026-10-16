# Next release

# 0.2.0 2026-10-16

 - Add CHANGELOG [#1](https://github.com/unckan/ckanext-serverterminal/pull/1)
 - Return 403 to non sysadmins instead of a 500 error [#2](https://github.com/unckan/ckanext-serverterminal/pull/2)
 - Add CI and fix locale dependent test [#3](https://github.com/unckan/ckanext-serverterminal/pull/3)
 - Add allowlisted CKAN commands and supervisor services, and split the page into clear sections (view logs, CKAN commands, services and history) [#5](https://github.com/unckan/ckanext-serverterminal/pull/5)
   - Default allowlist with CKAN core maintenance commands only; commands of other extensions are added per instance
   - Services are disabled unless `ckanext.serverterminal.services` is set
   - Support for several CKAN hosts: each run records its host
   - Remove PID and Python version from the page
   - README in English with all settings and the security model

# 0.1.0 2026-10-02

First release.

 - Read-only server log viewer for sysadmins at `/admin/server-terminal`, also listed as a tab in the admin panel
 - Logs restricted to an allowlist (`ckanext.serverterminal.log_paths`, default `/var/log/supervisor/*.log`)
 - Responses limited to 2000 lines and 512 KiB
 - Basic server info: hostname, PID, Python version and free disk space
 - Spanish translations
