import ckan.plugins as plugins


def test_plugin_is_loaded():
    assert plugins.plugin_loaded("serverterminal")


def test_blueprint_is_registered():
    plugin = plugins.get_plugin("serverterminal")
    assert plugin.get_blueprint()[0].name == "serverterminal"
