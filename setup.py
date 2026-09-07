from setuptools import setup, find_packages

setup(
    name='ckanext-serverterminal',
    version='0.1',
    description="Extension de CKAN para terminal de servidor",
    packages=find_packages(),
    namespace_packages=['ckanext'],
    entry_points='''
        [ckan.plugins]
        serverterminal=ckanext.serverterminal.plugin:ServerterminalPlugin
    ''',
)
