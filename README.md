# Bitácora de Procesos - Google Apps Script

Este repositorio contiene una versión web de la bitácora diseñada para **Google Apps Script**, usando Google Sheets como base de datos y una interfaz HTML simple.

## Qué archivos necesitas en Apps Script

Dentro del editor de Apps Script crea estos archivos y pega el contenido del repo:

- `Code.gs`
- `index.html`

## Pasos para publicarlo en Google Apps Script

1. Abre Google Drive y crea una hoja de cálculo nueva (será la base de datos).
2. Ve a **Extensiones → Apps Script**.
3. Elimina el archivo `Código.gs` que aparece por defecto.
4. Crea un archivo nuevo llamado **`Code.gs`** y pega el contenido del repo.
5. Crea un archivo HTML llamado **`index.html`** y pega el contenido del repo.
6. Guarda el proyecto.
7. En Apps Script, selecciona **Implementar → Nueva implementación → Aplicación web**.
8. En **Ejecutar como**, selecciona tu usuario.
9. En **Quién tiene acceso**, selecciona “Cualquiera con el enlace” o “Solo yo”.
10. Haz clic en **Implementar** y abre la URL que te da Apps Script.

## Qué hace esta versión

- Registra procesos con campos configurables.
- Guarda la bitácora de cada proceso.
- Permite editar la lista de campos (tipo y requerido).
- Gestiona acceso con usuario administrador y login.

## Copia del proyecto anterior (Python)

El archivo anterior basado en Python y SQLite se conserva como referencia en:

- `app_legacy.py`

Los scripts `run.bat`, `run.command` y `run.sh` son parte de esa versión anterior.
