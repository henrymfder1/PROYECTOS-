# Bitácora de Procesos - Firma de Abogados

Este proyecto incluye un programa en Python para registrar procesos legales, llevar una bitácora de actualizaciones y proteger el acceso con usuarios y contraseñas.

## Requisitos

- Python 3.9+

## Uso

1. Ejecuta el programa:

```bash
python app.py
```

2. También puedes ejecutar con doble clic:
   - Windows: `run.bat`
   - macOS: `run.command`
   - macOS/Linux: `run.sh`

3. Selecciona una opción del menú:
   - Registrar un nuevo proceso.
   - Listar procesos existentes.
   - Agregar una entrada de bitácora a un proceso.
   - Consultar la bitácora de un proceso.
   - Ajustar los campos que se piden y se listan.
   - Exportar la bitácora a CSV o PDF.
   - Gestionar usuarios y contraseñas.

## Ajustes de campos y validaciones

El archivo `config.json` guarda la lista de campos que se solicitan y muestran en los procesos. Desde el menú puedes reemplazar la lista completa con los campos que necesites y configurar:

- **Tipo**: `text`, `number` o `date` (formato `AAAA-MM-DD`).
- **Obligatorio**: define si el campo debe completarse o no.

## Exportar bitácora a Excel (CSV) o PDF

Desde el menú **Exportar bitácora**, el sistema crea:

- Archivos `.csv` (compatibles con Excel) para procesos y bitácora.
- Un archivo `.pdf` con el listado de procesos.

Los archivos se guardan en la carpeta `exports/`.

> Para PDF necesitas instalar `reportlab`:

```bash
pip install reportlab
```

## Usuarios y contraseñas

La primera vez que se ejecuta la aplicación, te pedirá crear un usuario administrador. Luego podrás:

- Crear usuarios.
- Listar usuarios.
- Resetear contraseñas.

Solo los administradores pueden gestionar usuarios.

## Crear un archivo `.exe`

Si deseas un ejecutable para Windows, puedes usar `pyinstaller`:

```bash
pip install pyinstaller
pyinstaller --onefile app.py
```

El ejecutable quedará en la carpeta `dist/`.

## Datos almacenados

La información se guarda en una base de datos SQLite local llamada `bitacora.db` en el mismo directorio.
