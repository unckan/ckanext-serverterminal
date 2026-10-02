import ckan.plugins as plugins


def test_plugin_is_loaded():
    assert plugins.plugin_loaded("serverterminal")


def test_blueprint_is_registered():
    plugin = plugins.get_plugin("serverterminal")
    assert plugin.get_blueprint()[0].name == "serverterminal"


def test_translation_catalog_is_registered():
    plugin = plugins.get_plugin("serverterminal")
    assert plugin.i18n_domain() == "ckanext-serverterminal"
    assert plugin.i18n_locales() == ["es"]
