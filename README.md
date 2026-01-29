# Bitácora de Procesos - Firma de Abogados (CLI Python)

Este proyecto incluye un programa en Python para registrar procesos legales, llevar una bitácora de actualizaciones, controlar gastos por proceso y proteger el acceso con usuarios y contraseñas.

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
   - Listar procesos (vista general o por filtros).
   - Agregar entradas de bitácora.
   - Gestionar estados con historial.
   - Vencimientos y alertas.
   - Gestionar campos (agregar, editar, borrar y reordenar).
   - Registrar y revisar gastos por proceso.
   - Reportes por fechas y cierres.
   - Exportar a CSV o PDF (incluye gastos agrupados).
   - Respaldos, restauración y reseteo del sistema.
   - Gestión de usuarios y contraseñas.

## Ajustes de campos y validaciones

Desde el menú **Ajustes de campos** puedes:

- Agregar campos sin borrar los existentes.
- Editar un campo específico (nombre, tipo, requerido).
- Eliminar campos si ya no se necesitan.
- Reordenar campos para cambiar el orden de captura y listado.
- Definir catálogos de opciones (listas predefinidas) para campos de texto.

Tipos de campo soportados:
- `text`
- `number`
- `date` (formato `AAAA-MM-DD`)

## Gastos por proceso

Cada proceso puede tener gastos (transporte u otros). El sistema:

- Permite que todos los usuarios registren gastos.
- Permite que solo el administrador edite montos o descripciones.
- Muestra el total de gastos por proceso en el listado.
- Permite exportar los gastos agrupados por el campo que selecciones (cliente, tipo, etc.).

## Listas y filtros

En el listado puedes ver:

- Vista general (todos los procesos).
- Filtro por ubicación de juzgado (si existe un campo con “juzgado”).
- Filtro por tipo de proceso (si existe un campo con “tipo”).
- Filtro por cualquier campo configurable.
- Eliminación de procesos (solo administrador).

## Estados con historial

Desde **Estados del proceso** puedes actualizar el estado y consultar el historial de cambios
con fecha y usuario.

## Vencimientos y alertas

Puedes registrar fechas clave (audiencias o plazos), ver vencimientos próximos y marcar
los completados.

## Reportes

- Procesos abiertos en un rango de fechas.
- Procesos cerrados por mes (basado en historial de estados).

## Exportar bitácora a Excel (CSV) o PDF

Desde el menú **Exportar bitácora**, el sistema crea:

- Archivos `.csv` (compatibles con Excel) para procesos, bitácora y gastos.
- Un archivo `.pdf` con el listado de procesos y total de gastos.
- Un `.csv` adicional con gastos agrupados por el campo que elijas.

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
- Asignar o quitar rol de administrador.

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

Cada vez que inicias la aplicación se crea un respaldo automático en la carpeta `backups/`.

Desde el menú **Respaldos y recuperación** puedes crear un respaldo manual, restaurar uno
existente o resetear toda la información (solo administrador).
