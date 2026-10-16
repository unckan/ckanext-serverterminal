# ckanext-serverterminal

Extensión de CKAN con herramientas para los administradores del sistema
(sysadmins). La pantalla queda en `/admin/server-terminal` y también aparece
como pestaña del panel de administración. Tiene cuatro secciones:

- **Ver logs**: muestra las últimas líneas de los archivos de log del servidor.
  Es de solo lectura.
- **Comandos de CKAN**: ejecuta subcomandos de la línea de comandos `ckan` que
  estén en una lista de permitidos (por ejemplo `search-index rebuild`).
- **Servicios**: muestra el estado de los procesos de supervisor y permite
  reiniciarlos.
- **Historial**: últimos comandos y reinicios, con el usuario que los ejecutó y
  su salida.

## Instalación

```bash
pip install -e /ruta/a/ckanext-serverterminal
```

Agregue `serverterminal` a `ckan.plugins` y reinicie CKAN:

```ini
ckan.plugins = ... serverterminal
```

## Configuración

```ini
# Logs que se pueden ver (rutas o patrones separados por comas)
ckanext.serverterminal.log_paths = /var/log/supervisor/*.log, /var/log/ckan/*.log

# Subcomandos de `ckan` permitidos, separados por comas. Cada entrada permite
# ese subcomando con cualquier argumento: "jobs list" permite "jobs list -l".
ckanext.serverterminal.ckan_commands = search-index rebuild, search-index check, jobs list

# Servicios de supervisor que se pueden reiniciar
ckanext.serverterminal.services = ckan ckan-worker yacron

# Tiempo máximo de cada comando, en segundos (por defecto 1800)
ckanext.serverterminal.command_timeout = 1800

# Carpeta donde se guarda cada ejecución (por defecto <ckan.storage_path>/serverterminal/runs)
ckanext.serverterminal.runs_dir = /ruta/a/carpeta

# Configuración de supervisor (por defecto /etc/supervisor/supervisord.conf)
ckanext.serverterminal.supervisor_config = /etc/supervisor/supervisord.conf
```

La lista de subcomandos permitidos por defecto está en
`ckanext/serverterminal/commands.py` (`DEFAULT_CKAN_COMMANDS`). Solo incluye
tareas de mantenimiento y consultas.

## Seguridad

- Solo los sysadmins pueden usar la pantalla; el resto recibe un 403.
- Los comandos **no pasan por una shell**: se ejecutan como una lista de
  argumentos, así que `&&`, `;`, `|` o `$(...)` no pueden encadenar otros
  comandos. Además se rechazan con un mensaje de error.
- Solo se ejecutan subcomandos de la lista de permitidos. Quedan afuera los que
  abren una consola de Python (`shell`), modifican la configuración
  (`config-tool`), escriben archivos (`generate`, `sass`, `asset`,
  `translation`), borran datos (`db clean`, `db downgrade`, `search-index clear`)
  o no terminan nunca (`jobs worker`, `run`).
- Corre un solo comando de CKAN a la vez, con tiempo máximo.
- Los pedidos desde el navegador requieren el token CSRF de CKAN.
- Cada ejecución queda registrada con el usuario en el log de CKAN y en el
  historial.
- Los procesos corren con el mismo usuario que CKAN (en la imagen de UNCKAN,
  `ckan`, que no es root).

Cada ejecución corre en un proceso separado, así que sigue funcionando aunque se
reinicie el servidor web de CKAN.

## Desarrollo

Las pruebas se ejecutan dentro de un entorno de desarrollo de CKAN con:

```bash
pytest --ckan-ini=test.ini
```

Para actualizar las traducciones:

```bash
python setup.py extract_messages
python setup.py update_catalog -l es
python setup.py compile_catalog
```
