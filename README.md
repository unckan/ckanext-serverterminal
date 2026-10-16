# ckanext-serverterminal

CKAN extension with server tools for system administrators (sysadmins). It adds
a page at `/admin/server-terminal`, also shown as a tab in the admin panel, with
these sections:

- **View logs**: shows the last lines of the server log files. Read only.
- **CKAN commands**: runs subcommands of the `ckan` command line that are in an
  allowlist (for example `search-index rebuild`).
- **Services**: shows the status of supervisor programs and lets you restart
  them. Only shown when configured.
- **History**: last commands and restarts, with the user who ran them, the host
  and the output.

It is not a full terminal: nothing outside the allowlists can be run.

## Requirements

- CKAN 2.10 or later (tested with 2.11).
- For the **Services** section: [supervisor](http://supervisord.org/), with
  `supervisorctl` usable by the user that runs CKAN.

## Installation

```bash
pip install -e /path/to/ckanext-serverterminal
```

Add `serverterminal` to `ckan.plugins` and restart CKAN:

```ini
ckan.plugins = ... serverterminal
```

## Configuration

All settings are optional.

| Setting | Default | Description |
|---|---|---|
| `ckanext.serverterminal.log_paths` | `/var/log/supervisor/*.log` | Log files that can be viewed: paths or glob patterns, separated by commas. |
| `ckanext.serverterminal.ckan_commands` | CKAN core list (see below) | Allowed `ckan` subcommands, separated by commas. Setting it replaces the default list. |
| `ckanext.serverterminal.services` | (empty) | Supervisor programs that can be restarted, separated by spaces. Empty hides the Services section. |
| `ckanext.serverterminal.command_timeout` | `1800` | Time limit for each run, in seconds. |
| `ckanext.serverterminal.runs_dir` | `<ckan.storage_path>/serverterminal/runs` | Folder where each run (command, output, result) is stored. |
| `ckanext.serverterminal.supervisor_config` | `/etc/supervisor/supervisord.conf` | Config file passed to `supervisorctl`. |

### Allowed CKAN commands

Each entry allows that subcommand with any argument or option: `jobs list`
allows `jobs list default`. The start of an allowed entry followed by `--help`
is also allowed (`jobs --help`).

The default list only has maintenance and read-only subcommands of CKAN core,
so it works in any instance:

```
search-index check, search-index list-orphans, search-index list-unindexed,
search-index clear-orphans, search-index rebuild, search-index show,
jobs list, jobs show, jobs cancel, jobs test,
sysadmin list, db version, plugin-info
```

Commands of other extensions are not allowed unless you add them. For example,
for an instance with XLoader and tracking:

```ini
ckanext.serverterminal.ckan_commands =
    search-index rebuild, search-index check, jobs list, jobs show, jobs cancel,
    sysadmin list, db version, plugin-info,
    xloader status, xloader submit, tracking update
```

Before adding an entry, check its options (`ckan <subcommand> --help`) and make
sure it does not give a sysadmin more power than the web interface already does.
Never add commands that:

- run code: `shell`
- edit the configuration: `config-tool`
- write files: `generate`, `sass`, `asset`, `translation`
- drop data in bulk: `db clean`, `db downgrade`, `search-index clear`, `db pending-migrations` (has `--apply`)
- never end: `jobs worker`, `run`

### Services

Program names depend on each deployment. Example for a deployment with
supervisor programs called `ckan`, `ckan-worker` and `yacron`:

```ini
ckanext.serverterminal.services = ckan ckan-worker yacron
```

Restarting the program that runs the CKAN web server makes the portal
unavailable for a few seconds. The restart still completes and is recorded in
the history.

## Security

- Only sysadmins can use the page; anybody else gets a 403.
- Commands **never go through a shell**: they run as a list of arguments, so
  `&&`, `;`, `|`, `>` or `$(...)` cannot chain other commands. They are also
  rejected with a clear error message.
- The program is always the `ckan` command of the running instance, with its
  config file (`ckan -c <config>`). Users only type what goes after it and
  cannot change the program or the config file.
- Only allowlisted subcommands and services are run (see above).
- One CKAN command at a time on each host, with a time limit.
- Requests from the browser need the CKAN CSRF token. Requests authenticated
  with an API token do not, as in CKAN core.
- Every run is written to the CKAN log (with the user) and kept in the history
  (last 50 runs).
- Commands run as the same system user as CKAN. Run CKAN as a non root user.
- Logs may contain sensitive data (errors, internal URLs). Only allow the log
  files that sysadmins need.

## Several CKAN hosts

If CKAN runs on more than one host (several containers or servers behind a load
balancer), each request may be answered by a different host. Logs, commands
and services always belong to the host that answers the request; the page
shows its name at the top and the history shows where each run happened.

- Set `ckanext.serverterminal.runs_dir` to a folder shared by all the hosts
  (the default, inside `ckan.storage_path`, usually is) so the history and the
  output of each run can be read from any of them.
- The status of a run that is still in progress can only be checked on the host
  that started it. From other hosts it is shown as "Unknown".
- Restarting a service only restarts it on the host that answered.

## How runs work

Each run starts as a separate process
(`python -m ckanext.serverterminal.runner <folder>`) and stores its command,
output and exit code in its own folder. It keeps running if the CKAN web server
is restarted.

## Development

Tests run inside a CKAN development environment:

```bash
pytest --ckan-ini=test.ini
```

To update translations:

```bash
python setup.py extract_messages
python setup.py update_catalog -l es
python setup.py compile_catalog
```
