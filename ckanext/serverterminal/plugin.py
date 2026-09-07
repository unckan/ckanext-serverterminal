import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit

from ckanext.serverterminal.blueprints import blueprints


class ServerterminalPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IBlueprint)

    def update_config(self, config_):
        toolkit.add_template_directory(config_, "templates")
        toolkit.add_resource("assets", "serverterminal")
        toolkit.add_ckan_admin_tab(
            config_, "serverterminal.index", "Terminal del servidor", icon="terminal"
        )

    def get_blueprint(self):
        return blueprints.get_blueprints()
