# ckanext-serverterminal

Extensión de CKAN que permite a los administradores consultar logs del servidor
desde una pantalla web de solo lectura. No permite ejecutar comandos del sistema.

## Instalación

```bash
pip install -e /ruta/a/ckanext-serverterminal
```

Agregue `serverterminal` a `ckan.plugins` y reinicie CKAN:

```ini
ckan.plugins = ... serverterminal
```

La pantalla quedará disponible en `/admin/server-terminal` y también aparecerá
como pestaña del panel de administración.

## Configuración

Por defecto se muestran los archivos `/var/log/supervisor/*.log`. Para cambiar
la lista permitida, configure rutas o patrones separados por comas:

```ini
ckanext.serverterminal.log_paths = /var/log/supervisor/*.log, /var/log/ckan/*.log
```

Solo se pueden solicitar archivos que coincidan con esta lista. Cada respuesta
está limitada a 2000 líneas y 512 KiB.

## Desarrollo

Las pruebas se ejecutan dentro de un entorno de desarrollo de CKAN con:

```bash
pytest --ckan-ini=test.ini
```

## Traducciones

Desde el entorno virtual de CKAN, actualice el catálogo plantilla y el catálogo
español con:

```bash
python setup.py extract_messages
python setup.py update_catalog -l es
```

Para crear el catálogo español por primera vez, use `python setup.py
init_catalog -l es`. Después de traducirlo, compile los archivos de runtime con
`python setup.py compile_catalog`.
