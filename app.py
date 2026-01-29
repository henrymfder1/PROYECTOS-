import csv
import json
import sqlite3
from datetime import datetime
from getpass import getpass
from hashlib import sha256
from pathlib import Path

DB_PATH = Path(__file__).with_name("bitacora.db")
CONFIG_PATH = Path(__file__).with_name("config.json")
EXPORTS_DIR = Path(__file__).with_name("exports")

DEFAULT_FIELDS = [
    {"name": "Número de expediente", "type": "text", "required": True},
    {"name": "Demandante", "type": "text", "required": True},
    {"name": "Demandado", "type": "text", "required": True},
    {"name": "Número de registro judicial", "type": "text", "required": True},
    {"name": "Identificador de juzgado", "type": "text", "required": True},
    {"name": "Abogado/Asociado asignado", "type": "text", "required": True},
    {"name": "Estado del proceso", "type": "text", "required": True},
]

FIELD_TYPES = {"text", "number", "date"}


def get_connection():
    return sqlite3.connect(DB_PATH)


def load_config():
    if not CONFIG_PATH.exists():
        save_config({"fields": DEFAULT_FIELDS})
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    return normalize_config(config)


def normalize_config(config):
    fields = config.get("fields", DEFAULT_FIELDS)
    normalized_fields = []
    if fields and isinstance(fields[0], str):
        for field in fields:
            normalized_fields.append(
                {"name": field, "type": "text", "required": True}
            )
    else:
        for field in fields:
            normalized_fields.append(
                {
                    "name": field.get("name", "Campo"),
                    "type": field.get("type", "text"),
                    "required": bool(field.get("required", True)),
                }
            )
    return {"fields": normalized_fields}


def save_config(config):
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                updated_at TEXT,
                updated_by TEXT,
                FOREIGN KEY (process_id) REFERENCES processes(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS log_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER NOT NULL,
                entry_date TEXT NOT NULL,
                note TEXT NOT NULL,
                FOREIGN KEY (process_id) REFERENCES processes(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )


def prompt(text):
    return input(f"{text}: ").strip()


def hash_password(password, salt):
    return sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def create_user(username, password, is_admin=False):
    salt = sha256(str(datetime.now().timestamp()).encode("utf-8")).hexdigest()
    password_hash = hash_password(password, salt)
    created_at = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (username, password_hash, salt, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, password_hash, salt, 1 if is_admin else 0, created_at),
        )


def ensure_admin_user():
    with get_connection() as conn:
        users = conn.execute("SELECT id FROM users").fetchall()
    if users:
        return
    print("\n--- Configuración inicial de usuarios ---")
    while True:
        username = prompt("Crea un usuario administrador")
        if not username:
            print("El usuario es obligatorio.")
            continue
        password = getpass("Crea una contraseña: ")
        confirm = getpass("Confirma la contraseña: ")
        if not password:
            print("La contraseña es obligatoria.")
            continue
        if password != confirm:
            print("Las contraseñas no coinciden.")
            continue
        create_user(username, password, is_admin=True)
        print("Usuario administrador creado.\n")
        break


def authenticate():
    print("\n--- Inicio de sesión ---")
    username = prompt("Usuario")
    password = getpass("Contraseña: ")
    with get_connection() as conn:
        user = conn.execute(
            """
            SELECT id, username, password_hash, salt, is_admin
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
    if not user:
        print("Usuario o contraseña incorrectos.\n")
        return None
    user_id, username, password_hash, salt, is_admin = user
    if hash_password(password, salt) != password_hash:
        print("Usuario o contraseña incorrectos.\n")
        return None
    return {"id": user_id, "username": username, "is_admin": bool(is_admin)}


def validate_field(field, value):
    if not value:
        return False, "El campo es obligatorio."
    field_type = field.get("type", "text")
    if field_type == "number":
        try:
            float(value)
        except ValueError:
            return False, "Debe ser un número."
    elif field_type == "date":
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return False, "Debe tener formato AAAA-MM-DD."
    return True, ""


def prompt_fields(fields):
    data = {}
    for field in fields:
        name = field["name"]
        field_type = field.get("type", "text")
        required = field.get("required", True)
        hint = ""
        if field_type == "date":
            hint = " (AAAA-MM-DD)"
        if field_type == "number":
            hint = " (número)"

        while True:
            value = prompt(f"{name}{hint}")
            if not value and not required:
                data[name] = ""
                break
            is_valid, error = validate_field(field, value)
            if not is_valid:
                print(f"{error}\n")
                continue
            data[name] = value
            break
    return data


def add_process():
    config = load_config()
    fields = config.get("fields", DEFAULT_FIELDS)
    print("\n--- Nuevo proceso ---")
    data = prompt_fields(fields)

    created_at = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO processes (data_json, created_at)
            VALUES (?, ?)
            """,
            (json.dumps(data, ensure_ascii=False), created_at),
        )
    print("Proceso registrado.\n")


def get_expense_totals():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT process_id, COALESCE(SUM(amount), 0)
            FROM expenses
            GROUP BY process_id
            """
        ).fetchall()
    return {process_id: total for process_id, total in rows}


def list_processes(processes=None):
    config = load_config()
    fields = config.get("fields", DEFAULT_FIELDS)
    field_names = [field["name"] for field in fields]
    if processes is None:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, data_json, created_at
                FROM processes
                ORDER BY created_at DESC
                """
            ).fetchall()
    else:
        rows = processes

    expense_totals = get_expense_totals()

    if not rows:
        print("No hay procesos registrados.\n")
        return

    print("\n--- Procesos ---")
    for row in rows:
        process_id, data_json, created_at = row
        data = json.loads(data_json)
        columns = " | ".join([data.get(field, "-") for field in field_names])
        total_gastos = expense_totals.get(process_id, 0)
        print(f"[{process_id}] {columns} | {created_at} | gastos: {total_gastos:.2f}")
    print()


def add_log_entry():
    list_processes()
    process_id = prompt("ID del proceso para la bitácora")
    note = prompt("Nota/actualización")

    if not process_id.isdigit() or not note:
        print("Debes ingresar un ID válido y una nota.\n")
        return

    entry_date = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        process = conn.execute(
            "SELECT id FROM processes WHERE id = ?", (process_id,)
        ).fetchone()
        if not process:
            print("El proceso no existe.\n")
            return
        conn.execute(
            """
            INSERT INTO log_entries (process_id, entry_date, note)
            VALUES (?, ?, ?)
            """,
            (process_id, entry_date, note),
        )
    print("Entrada de bitácora registrada.\n")


def view_log():
    list_processes()
    process_id = prompt("ID del proceso a consultar")
    if not process_id.isdigit():
        print("ID inválido.\n")
        return

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT entry_date, note
            FROM log_entries
            WHERE process_id = ?
            ORDER BY entry_date DESC
            """,
            (process_id,),
        ).fetchall()

    if not rows:
        print("No hay entradas de bitácora para este proceso.\n")
        return

    print("\n--- Bitácora ---")
    for entry_date, note in rows:
        print(f"{entry_date} | {note}")
    print()


def configure_fields():
    config = load_config()
    fields = config.get("fields", DEFAULT_FIELDS)
    print("\n--- Ajustes de campos ---")
    if not fields:
        fields = []

    while True:
        print("Campos actuales:")
        for index, field in enumerate(fields, start=1):
            required_label = "sí" if field.get("required", True) else "no"
            print(
                f"{index}. {field['name']} (tipo: {field.get('type', 'text')}, "
                f"obligatorio: {required_label})"
            )
        print("\nOpciones:")
        print("1. Agregar campo")
        print("2. Editar campo")
        print("3. Eliminar campo")
        print("4. Reordenar campo")
        print("5. Volver")
        choice = prompt("Selecciona una opción")

        if choice == "1":
            name = prompt("Nombre del nuevo campo")
            if not name:
                print("El nombre es obligatorio.\n")
                continue
            field_type = prompt("Tipo (text/number/date)") or "text"
            if field_type not in FIELD_TYPES:
                print("Tipo inválido, se usará 'text'.")
                field_type = "text"
            required_raw = prompt("¿Obligatorio? (s/n)") or "s"
            required = required_raw.lower().startswith("s")
            position_raw = prompt("Posición (1 = inicio, enter = final)")
            if position_raw.isdigit():
                position = max(1, min(int(position_raw), len(fields) + 1)) - 1
                fields.insert(position, {"name": name, "type": field_type, "required": required})
            else:
                fields.append({"name": name, "type": field_type, "required": required})
            save_config({"fields": fields})
            print("Campo agregado.\n")
        elif choice == "2":
            index_raw = prompt("Número del campo a editar")
            if not index_raw.isdigit():
                print("Número inválido.\n")
                continue
            index = int(index_raw) - 1
            if index < 0 or index >= len(fields):
                print("Número fuera de rango.\n")
                continue
            field = fields[index]
            name = prompt(f"Nombre ({field['name']})") or field["name"]
            field_type = prompt(f"Tipo ({field.get('type', 'text')})") or field.get("type", "text")
            if field_type not in FIELD_TYPES:
                print("Tipo inválido, se mantiene el anterior.")
                field_type = field.get("type", "text")
            required_raw = prompt(
                f"¿Obligatorio? (s/n) ({'s' if field.get('required', True) else 'n'})"
            )
            if required_raw:
                required = required_raw.lower().startswith("s")
            else:
                required = field.get("required", True)
            fields[index] = {"name": name, "type": field_type, "required": required}
            save_config({"fields": fields})
            print("Campo actualizado.\n")
        elif choice == "3":
            index_raw = prompt("Número del campo a eliminar")
            if not index_raw.isdigit():
                print("Número inválido.\n")
                continue
            index = int(index_raw) - 1
            if index < 0 or index >= len(fields):
                print("Número fuera de rango.\n")
                continue
            removed = fields.pop(index)
            save_config({"fields": fields})
            print(f"Campo eliminado: {removed['name']}\n")
        elif choice == "4":
            index_raw = prompt("Número del campo a mover")
            if not index_raw.isdigit():
                print("Número inválido.\n")
                continue
            index = int(index_raw) - 1
            if index < 0 or index >= len(fields):
                print("Número fuera de rango.\n")
                continue
            new_pos_raw = prompt("Nueva posición (1 = inicio)")
            if not new_pos_raw.isdigit():
                print("Posición inválida.\n")
                continue
            new_pos = max(1, min(int(new_pos_raw), len(fields))) - 1
            field = fields.pop(index)
            fields.insert(new_pos, field)
            save_config({"fields": fields})
            print("Campo reordenado.\n")
        elif choice == "5":
            print()
            return
        else:
            print("Opción inválida.\n")
            continue


def filter_processes_by_field(field_name, value):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, data_json, created_at
            FROM processes
            ORDER BY created_at DESC
            """
        ).fetchall()
    filtered = []
    for process_id, data_json, created_at in rows:
        data = json.loads(data_json)
        if str(data.get(field_name, "")).strip().lower() == value.strip().lower():
            filtered.append((process_id, data_json, created_at))
    return filtered


def list_processes_menu():
    config = load_config()
    fields = config.get("fields", DEFAULT_FIELDS)
    field_names = [field["name"] for field in fields]
    print("\n--- Listado de procesos ---")
    print("1. Vista general")
    print("2. Filtrar por ubicación de juzgado")
    print("3. Filtrar por tipo de proceso")
    print("4. Filtrar por cualquier campo")
    choice = prompt("Selecciona una opción")
    if choice == "1":
        list_processes()
    elif choice == "2":
        field = next(
            (name for name in field_names if "juzgado" in name.lower()),
            None,
        )
        if not field:
            print("No existe un campo de juzgado en la configuración.\n")
            return
        value = prompt(f"Valor para {field}")
        list_processes(filter_processes_by_field(field, value))
    elif choice == "3":
        field = next(
            (name for name in field_names if "tipo" in name.lower()),
            None,
        )
        if not field:
            print("No existe un campo de tipo de proceso en la configuración.\n")
            return
        value = prompt(f"Valor para {field}")
        list_processes(filter_processes_by_field(field, value))
    elif choice == "4":
        print("Campos disponibles:")
        for index, field in enumerate(field_names, start=1):
            print(f"{index}. {field}")
        index_raw = prompt("Número del campo")
        if not index_raw.isdigit():
            print("Número inválido.\n")
            return
        index = int(index_raw) - 1
        if index < 0 or index >= len(field_names):
            print("Número fuera de rango.\n")
            return
        value = prompt("Valor a buscar")
        list_processes(filter_processes_by_field(field_names[index], value))
    else:
        print("Opción inválida.\n")


def add_expense(user):
    list_processes()
    process_id = prompt("ID del proceso para el gasto")
    amount_raw = prompt("Monto del gasto")
    description = prompt("Descripción del gasto")
    if not process_id.isdigit():
        print("ID inválido.\n")
        return
    try:
        amount = float(amount_raw)
    except ValueError:
        print("Monto inválido.\n")
        return
    if not description:
        print("La descripción es obligatoria.\n")
        return
    created_at = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        process = conn.execute(
            "SELECT id FROM processes WHERE id = ?", (process_id,)
        ).fetchone()
        if not process:
            print("El proceso no existe.\n")
            return
        conn.execute(
            """
            INSERT INTO expenses (process_id, amount, description, created_at, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (process_id, amount, description, created_at, user["username"]),
        )
    print("Gasto registrado.\n")


def list_expenses(process_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, amount, description, created_at, created_by, updated_at, updated_by
            FROM expenses
            WHERE process_id = ?
            ORDER BY created_at DESC
            """,
            (process_id,),
        ).fetchall()

    if not rows:
        print("No hay gastos para este proceso.\n")
        return []

    print("\n--- Gastos ---")
    total = 0
    for expense_id, amount, description, created_at, created_by, updated_at, updated_by in rows:
        total += amount
        updated_label = ""
        if updated_at:
            updated_label = f" | modificado: {updated_at} por {updated_by}"
        print(
            f"[{expense_id}] {amount:.2f} | {description} | {created_at} | {created_by}{updated_label}"
        )
    print(f"Total de gastos: {total:.2f}\n")
    return rows


def view_expenses():
    list_processes()
    process_id = prompt("ID del proceso a consultar")
    if not process_id.isdigit():
        print("ID inválido.\n")
        return
    list_expenses(process_id)


def edit_expense(user):
    if not user.get("is_admin"):
        print("Solo un administrador puede editar gastos.\n")
        return
    list_processes()
    process_id = prompt("ID del proceso")
    if not process_id.isdigit():
        print("ID inválido.\n")
        return
    rows = list_expenses(process_id)
    if not rows:
        return
    expense_id_raw = prompt("ID del gasto a modificar")
    if not expense_id_raw.isdigit():
        print("ID inválido.\n")
        return
    amount_raw = prompt("Nuevo monto (enter para mantener)")
    description = prompt("Nueva descripción (enter para mantener)")
    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT amount, description FROM expenses
            WHERE id = ? AND process_id = ?
            """,
            (expense_id_raw, process_id),
        ).fetchone()
        if not existing:
            print("Gasto no encontrado.\n")
            return
        amount = existing[0]
        new_description = existing[1]
        if amount_raw:
            try:
                amount = float(amount_raw)
            except ValueError:
                print("Monto inválido.\n")
                return
        if description:
            new_description = description
        updated_at = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            """
            UPDATE expenses
            SET amount = ?, description = ?, updated_at = ?, updated_by = ?
            WHERE id = ? AND process_id = ?
            """,
            (amount, new_description, updated_at, user["username"], expense_id_raw, process_id),
        )
    print("Gasto actualizado.\n")


def export_to_csv():
    config = load_config()
    fields = config.get("fields", DEFAULT_FIELDS)
    field_names = [field["name"] for field in fields]
    EXPORTS_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    processes_path = EXPORTS_DIR / f"procesos_{timestamp}.csv"
    logs_path = EXPORTS_DIR / f"bitacora_{timestamp}.csv"
    expenses_path = EXPORTS_DIR / f"gastos_{timestamp}.csv"

    with get_connection() as conn:
        processes = conn.execute(
            "SELECT id, data_json, created_at FROM processes ORDER BY created_at DESC"
        ).fetchall()
        logs = conn.execute(
            """
            SELECT log_entries.process_id, log_entries.entry_date, log_entries.note
            FROM log_entries
            ORDER BY log_entries.entry_date DESC
            """
        ).fetchall()
        expenses = conn.execute(
            """
            SELECT process_id, amount, description, created_at, created_by, updated_at, updated_by
            FROM expenses
            ORDER BY created_at DESC
            """
        ).fetchall()

    totals = get_expense_totals()
    with processes_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ID"] + field_names + ["Fecha de creación", "Total gastos"])
        for process_id, data_json, created_at in processes:
            data = json.loads(data_json)
            writer.writerow(
                [process_id]
                + [data.get(field, "") for field in field_names]
                + [created_at, f"{totals.get(process_id, 0):.2f}"]
            )

    with logs_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ID Proceso", "Fecha", "Nota"])
        for process_id, entry_date, note in logs:
            writer.writerow([process_id, entry_date, note])

    with expenses_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "ID Proceso",
                "Monto",
                "Descripción",
                "Creado",
                "Creado por",
                "Actualizado",
                "Actualizado por",
            ]
        )
        for process_id, amount, description, created_at, created_by, updated_at, updated_by in expenses:
            writer.writerow(
                [
                    process_id,
                    f"{amount:.2f}",
                    description,
                    created_at,
                    created_by,
                    updated_at or "",
                    updated_by or "",
                ]
            )

    print(f"Exportación CSV creada en: {processes_path}")
    print(f"Exportación CSV de bitácora en: {logs_path}\n")
    print(f"Exportación CSV de gastos en: {expenses_path}\n")


def export_to_pdf():
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
    except ImportError:
        print("Para exportar a PDF instala reportlab: pip install reportlab\n")
        return

    config = load_config()
    fields = config.get("fields", DEFAULT_FIELDS)
    field_names = [field["name"] for field in fields]
    EXPORTS_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = EXPORTS_DIR / f"procesos_{timestamp}.pdf"

    with get_connection() as conn:
        processes = conn.execute(
            "SELECT id, data_json, created_at FROM processes ORDER BY created_at DESC"
        ).fetchall()

    pdf = canvas.Canvas(str(pdf_path), pagesize=letter)
    width, height = letter
    y = height - inch

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(inch, y, "Bitácora de Procesos")
    y -= 0.5 * inch

    totals = get_expense_totals()
    pdf.setFont("Helvetica", 10)
    for process_id, data_json, created_at in processes:
        data = json.loads(data_json)
        pdf.drawString(inch, y, f"ID: {process_id} | Fecha: {created_at}")
        y -= 0.25 * inch
        for field in field_names:
            pdf.drawString(inch, y, f"{field}: {data.get(field, '')}")
            y -= 0.2 * inch
            if y < inch:
                pdf.showPage()
                pdf.setFont("Helvetica", 10)
                y = height - inch
        pdf.drawString(inch, y, f"Total de gastos: {totals.get(process_id, 0):.2f}")
        y -= 0.2 * inch
        y -= 0.2 * inch
        if y < inch:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = height - inch

    pdf.save()
    print(f"Exportación PDF creada en: {pdf_path}\n")


def export_menu():
    print("\n--- Exportar bitácora ---")
    print("1. Exportar a CSV (Excel)")
    print("2. Exportar a PDF")
    choice = prompt("Selecciona una opción")
    if choice == "1":
        export_to_csv()
    elif choice == "2":
        export_to_pdf()
    else:
        print("Opción inválida.\n")


def expenses_menu(user):
    print("\n--- Gastos por proceso ---")
    print("1. Registrar gasto")
    print("2. Ver gastos por proceso")
    print("3. Editar gasto (admin)")
    choice = prompt("Selecciona una opción")
    if choice == "1":
        add_expense(user)
    elif choice == "2":
        view_expenses()
    elif choice == "3":
        edit_expense(user)
    else:
        print("Opción inválida.\n")


def list_users():
    with get_connection() as conn:
        users = conn.execute(
            "SELECT id, username, is_admin, created_at FROM users ORDER BY created_at"
        ).fetchall()
    print("\n--- Usuarios ---")
    for user_id, username, is_admin, created_at in users:
        role = "admin" if is_admin else "usuario"
        print(f"[{user_id}] {username} | {role} | {created_at}")
    print()


def add_user():
    username = prompt("Nuevo usuario")
    if not username:
        print("El usuario es obligatorio.\n")
        return
    password = getpass("Contraseña: ")
    confirm = getpass("Confirma la contraseña: ")
    if not password or password != confirm:
        print("Las contraseñas no coinciden.\n")
        return
    is_admin = prompt("¿Es administrador? (s/n)")
    try:
        create_user(username, password, is_admin=is_admin.lower().startswith("s"))
    except sqlite3.IntegrityError:
        print("Ese usuario ya existe.\n")
        return
    print("Usuario creado.\n")


def reset_password():
    username = prompt("Usuario para resetear contraseña")
    if not username:
        print("El usuario es obligatorio.\n")
        return
    password = getpass("Nueva contraseña: ")
    confirm = getpass("Confirma la contraseña: ")
    if not password or password != confirm:
        print("Las contraseñas no coinciden.\n")
        return
    salt = sha256(str(datetime.now().timestamp()).encode("utf-8")).hexdigest()
    password_hash = hash_password(password, salt)
    with get_connection() as conn:
        updated = conn.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
            (password_hash, salt, username),
        )
    if updated.rowcount == 0:
        print("Usuario no encontrado.\n")
    else:
        print("Contraseña actualizada.\n")


def manage_users(user):
    if not user.get("is_admin"):
        print("Solo un administrador puede gestionar usuarios.\n")
        return
    print("\n--- Gestión de usuarios ---")
    print("1. Listar usuarios")
    print("2. Crear usuario")
    print("3. Resetear contraseña")
    choice = prompt("Selecciona una opción")
    if choice == "1":
        list_users()
    elif choice == "2":
        add_user()
    elif choice == "3":
        reset_password()
    else:
        print("Opción inválida.\n")


def main():
    init_db()
    ensure_admin_user()
    user = None
    while not user:
        user = authenticate()

    actions = {
        "1": ("Registrar nuevo proceso", add_process),
        "2": ("Listar procesos", list_processes_menu),
        "3": ("Agregar entrada de bitácora", add_log_entry),
        "4": ("Ver bitácora de un proceso", view_log),
        "5": ("Ajustes de campos", configure_fields),
        "6": ("Gastos por proceso", lambda: expenses_menu(user)),
        "7": ("Exportar bitácora", export_menu),
        "8": ("Gestión de usuarios", lambda: manage_users(user)),
        "9": ("Salir", None),
    }

    while True:
        print("\n=== Bitácora de Procesos ===")
        for key, (label, _) in actions.items():
            print(f"{key}. {label}")
        choice = prompt("Selecciona una opción")
        action = actions.get(choice)
        if not action:
            print("Opción inválida.\n")
            continue
        if choice == "9":
            print("Hasta luego.")
            break
        action[1]()


if __name__ == "__main__":
    main()
