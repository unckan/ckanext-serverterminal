import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from ckan.lib.plugins import DefaultTranslation

from ckanext.serverterminal.blueprints import blueprints


class ServerterminalPlugin(plugins.SingletonPlugin, DefaultTranslation):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.ITranslation)

    def i18n_locales(self):
        return ["es"]

    def i18n_domain(self):
        return "ckanext-serverterminal"

    def update_config(self, config_):
        toolkit.add_template_directory(config_, "templates")
        toolkit.add_resource("assets", "serverterminal")

    def get_blueprint(self):
        return blueprints.get_blueprints()
