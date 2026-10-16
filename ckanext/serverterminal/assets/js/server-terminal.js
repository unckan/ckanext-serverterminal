(function (ckan, $) {
  'use strict';

  // Logs, command output and history come from the server and may contain HTML
  // (e.g. a dataset title). Always insert them with .text() or .attr(), never .html().

  var RUN_STARTED = 'serverterminal:run-started';
  var SHOW_RUN = 'serverterminal:show-run';

  function csrfHeaders() {
    var field = $('meta[name=csrf_field_name]').attr('content');
    var token = $('meta[name="' + field + '"]').attr('content');
    return token ? { 'X-CSRFToken': token } : {};
  }

  function postJSON(url, data) {
    return $.ajax({
      url: url,
      method: 'POST',
      contentType: 'application/json',
      dataType: 'json',
      headers: csrfHeaders(),
      data: JSON.stringify(data || {})
    });
  }

  function errorMessage(response, fallback) {
    return (response.responseJSON && response.responseJSON.error) || fallback;
  }

  function statusLabel(module, status) {
    var labels = {
      running: module._('Running'),
      success: module._('Finished'),
      failed: module._('Failed'),
      timeout: module._('Time limit exceeded'),
      interrupted: module._('Interrupted'),
      unknown: module._('Unknown (started on another host)')
    };
    return labels[status] || status;
  }

  function setBadge(el, status, text) {
    el.text(text).attr('data-status', status);
  }

  // View logs
  ckan.module('server-terminal-logs', function ($) {
    return {
      initialize: function () {
        this.output = this.el.find('[data-terminal-output]');
        this.status = this.el.find('[data-terminal-status]');
        if (!this.output.length) return;

        this.el.on('change', '[data-terminal-source], [data-terminal-lines]', $.proxy(this.load, this));
        this.el.on('click', '[data-terminal-action="refresh"]', $.proxy(this.load, this));
        this.load();
        this.timer = window.setInterval($.proxy(this.tick, this), 3000);
      },

      teardown: function () {
        window.clearInterval(this.timer);
      },

      tick: function () {
        if (this.el.find('[data-terminal-auto-refresh]').is(':checked') && !document.hidden) {
          this.load();
        }
      },

      load: function () {
        var self = this;
        if (this.loading) return;
        this.loading = true;
        $.getJSON(this.options.endpoint, {
          source: this.el.find('[data-terminal-source]').val(),
          lines: this.el.find('[data-terminal-lines]').val()
        }).done(function (data) {
          self.output.text(data.content || self._('(empty file)'));
          self.status.text(
            self._('File: %(file)s - Updated: %(time)s - Size: %(size)s bytes', {
              file: data.source,
              time: new Date().toLocaleTimeString(),
              size: data.size
            })
          );
          if (self.el.find('[data-terminal-follow]').is(':checked')) {
            var screen = self.el.find('.server-terminal__screen')[0];
            screen.scrollTop = screen.scrollHeight;
          }
        }).fail(function (response) {
          self.status.text(errorMessage(response, self._('Could not load logs.')));
        }).always(function () {
          self.loading = false;
        });
      }
    };
  });

  // CKAN commands: run a subcommand and follow its output
  ckan.module('server-terminal-commands', function ($) {
    return {
      initialize: function () {
        this.input = this.el.find('[data-terminal-command]');
        this.panel = this.el.find('[data-terminal-run]');
        this.el.on('submit', '[data-terminal-command-form]', $.proxy(this.submit, this));
        this.el.on('click', '[data-terminal-fill]', $.proxy(this.fill, this));
        this.sandbox.subscribe(SHOW_RUN, $.proxy(this.follow, this));
      },

      teardown: function () {
        window.clearTimeout(this.timer);
        this.sandbox.unsubscribe(SHOW_RUN, $.proxy(this.follow, this));
      },

      fill: function (event) {
        this.input.val($(event.currentTarget).attr('data-terminal-fill')).trigger('focus');
      },

      submit: function (event) {
        var self = this;
        var command = $.trim(this.input.val());
        event.preventDefault();
        if (!command) return;
        if (!window.confirm(this._('Run "ckan %(command)s" on the server?', { command: command }))) return;

        postJSON(this.options.runEndpoint, { command: command }).done(function (run) {
          self.sandbox.publish(RUN_STARTED, run);
          self.follow(run.id);
        }).fail(function (response) {
          self.showMessage('ckan ' + command, errorMessage(response, self._('Could not run the command.')));
        });
      },

      showMessage: function (command, message) {
        this.panel.prop('hidden', false);
        this.panel.find('[data-terminal-run-command]').text(command);
        setBadge(this.panel.find('[data-terminal-run-status]'), 'failed', this._('Not run'));
        this.panel.find('[data-terminal-run-output]').text(message);
      },

      follow: function (runId) {
        var self = this;
        var url = this.options.runDetailEndpoint.replace('RUN', encodeURIComponent(runId));
        window.clearTimeout(this.timer);
        this.panel.prop('hidden', false);

        $.getJSON(url).done(function (run) {
          self.panel.find('[data-terminal-run-command]').text(run.command);
          setBadge(self.panel.find('[data-terminal-run-status]'), run.status, statusLabel(self, run.status) +
            (run.exit_code !== undefined && run.status !== 'running' ? ' (' + self._('exit code %(code)s', { code: run.exit_code }) + ')' : ''));
          self.panel.find('[data-terminal-run-output]').text(run.output || self._('(no output yet)'));
          if (run.status === 'running') {
            self.timer = window.setTimeout(function () { self.follow(runId); }, 2000);
          } else {
            self.sandbox.publish(RUN_STARTED, run);
          }
        }).fail(function (response) {
          if (response.status === 404) {
            // Another CKAN host answered and it does not share the runs folder
            setBadge(self.panel.find('[data-terminal-run-status]'), 'unknown', self._('Unknown'));
            self.panel.find('[data-terminal-run-output]').text(errorMessage(response, '') + ' ' +
              self._('The run is not available on the host that answered. If CKAN runs on several hosts, set ckanext.serverterminal.runs_dir to a shared folder.'));
            return;
          }
          // The web server may be restarting: try again
          self.timer = window.setTimeout(function () { self.follow(runId); }, 3000);
        });
      }
    };
  });

  // Services managed by supervisor
  ckan.module('server-terminal-services', function ($) {
    return {
      initialize: function () {
        this.el.on('click', '[data-terminal-restart]', $.proxy(this.restart, this));
        this.el.on('click', '[data-terminal-action="refresh-services"]', $.proxy(this.load, this));
        this.load();
      },

      load: function () {
        var self = this;
        $.getJSON(this.options.endpoint).done(function (data) {
          $.each(data.services, function (i, service) {
            var row = self.el.find('[data-terminal-service="' + service.name + '"]');
            setBadge(row.find('[data-terminal-service-state]'), service.state.toLowerCase(), service.state);
            row.find('[data-terminal-service-details]').text(service.details);
          });
        }).fail(function () {
          self.el.find('[data-terminal-service-state]').text(self._('Unknown'));
        });
      },

      restart: function (event) {
        var self = this;
        var name = $(event.currentTarget).attr('data-terminal-restart');
        if (!window.confirm(this._('Restart the service "%(name)s"?', { name: name }))) return;

        var url = this.options.restartEndpoint.replace('SERVICE', encodeURIComponent(name));
        postJSON(url).done(function (run) {
          self.sandbox.publish(RUN_STARTED, run);
          self.sandbox.publish(SHOW_RUN, run.id);
          self.el.find('[data-terminal-service="' + name + '"] [data-terminal-service-state]').text(self._('Restarting...'));
          window.setTimeout($.proxy(self.load, self), 5000);
          window.setTimeout($.proxy(self.load, self), 15000);
        }).fail(function (response) {
          window.alert(errorMessage(response, self._('Could not restart the service.')));
        });
      }
    };
  });

  // History of runs
  ckan.module('server-terminal-history', function ($) {
    return {
      initialize: function () {
        this.body = this.el.find('[data-terminal-runs]');
        this.el.on('click', '[data-terminal-show-run]', $.proxy(this.show, this));
        this.sandbox.subscribe(RUN_STARTED, $.proxy(this.load, this));
        this.load();
      },

      teardown: function () {
        this.sandbox.unsubscribe(RUN_STARTED, $.proxy(this.load, this));
      },

      show: function (event) {
        this.sandbox.publish(SHOW_RUN, $(event.currentTarget).attr('data-terminal-show-run'));
        var target = document.getElementById('server-terminal-commands');
        if (target) target.scrollIntoView();
      },

      load: function () {
        var self = this;
        $.getJSON(this.options.endpoint).done(function (data) {
          self.body.empty();
          if (!data.runs.length) {
            self.body.append($('<tr>').append($('<td colspan="6">').text(self._('Nothing has been run yet.'))));
            return;
          }
          $.each(data.runs, function (i, run) {
            var badge = $('<span class="server-terminal__badge">');
            setBadge(badge, run.status, statusLabel(self, run.status));
            self.body.append($('<tr>').append(
              $('<td>').text(new Date(run.started * 1000).toLocaleString()),
              $('<td>').text(run.user),
              $('<td>').text(run.host || ''),
              $('<td>').append($('<code>').text(run.command)),
              $('<td>').append(badge),
              $('<td class="text-end text-right">').append(
                $('<button type="button" class="btn btn-link btn-sm">')
                  .attr('data-terminal-show-run', run.id)
                  .text(self._('View output'))
              )
            ));
          });
        });
      }
    };
  });
})(this.ckan, this.jQuery);
