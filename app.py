import csv
import json
import sqlite3
import shutil
from datetime import datetime
from getpass import getpass
from hashlib import sha256
from pathlib import Path

DB_PATH = Path(__file__).with_name("bitacora.db")
CONFIG_PATH = Path(__file__).with_name("config.json")
EXPORTS_DIR = Path(__file__).with_name("exports")
BACKUPS_DIR = Path(__file__).with_name("backups")

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
                {"name": field, "type": "text", "required": True, "options": []}
            )
    else:
        for field in fields:
            normalized_fields.append(
                {
                    "name": field.get("name", "Campo"),
                    "type": field.get("type", "text"),
                    "required": bool(field.get("required", True)),
                    "options": field.get("options", []) or [],
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
            CREATE TABLE IF NOT EXISTS status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                FOREIGN KEY (process_id) REFERENCES processes(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER NOT NULL,
                due_date TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                completed_at TEXT,
                completed_by TEXT,
                is_completed INTEGER NOT NULL DEFAULT 0,
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
    options = field.get("options") or []
    if options and value not in options:
        return False, f"Debe ser una de las opciones: {', '.join(options)}."
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
        options = field.get("options") or []
        hint = ""
        if field_type == "date":
            hint = " (AAAA-MM-DD)"
        if field_type == "number":
            hint = " (número)"
        if options:
            hint = f" (opciones: {', '.join(options)})"

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


def backup_database(auto=False):
    if not DB_PATH.exists():
        return
    BACKUPS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUPS_DIR / f"bitacora_{timestamp}.db"
    shutil.copy2(DB_PATH, backup_path)
    label = "Respaldo automático creado" if auto else "Respaldo creado"
    print(f"{label}: {backup_path}\n")


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
            options = []
            if field_type == "text":
                options_raw = prompt("Opciones separadas por coma (enter para libre)")
                if options_raw:
                    options = [opt.strip() for opt in options_raw.split(",") if opt.strip()]
            position_raw = prompt("Posición (1 = inicio, enter = final)")
            if position_raw.isdigit():
                position = max(1, min(int(position_raw), len(fields) + 1)) - 1
                fields.insert(
                    position,
                    {
                        "name": name,
                        "type": field_type,
                        "required": required,
                        "options": options,
                    },
                )
            else:
                fields.append(
                    {
                        "name": name,
                        "type": field_type,
                        "required": required,
                        "options": options,
                    }
                )
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
            options = field.get("options", [])
            if field_type == "text":
                options_raw = prompt(
                    f"Opciones separadas por coma (actual: {', '.join(options) or 'libre'})"
                )
                if options_raw:
                    options = [opt.strip() for opt in options_raw.split(",") if opt.strip()]
                elif options_raw == "":
                    options = []
            else:
                options = []
            fields[index] = {
                "name": name,
                "type": field_type,
                "required": required,
                "options": options,
            }
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


def find_field_by_keyword(fields, keyword):
    return next((field for field in fields if keyword in field["name"].lower()), None)


def update_process_status(user):
    config = load_config()
    fields = config.get("fields", DEFAULT_FIELDS)
    status_field = find_field_by_keyword(fields, "estado")
    if not status_field:
        print("No existe un campo de estado en la configuración.\n")
        return
    list_processes()
    process_id = prompt("ID del proceso a actualizar")
    if not process_id.isdigit():
        print("ID inválido.\n")
        return
    with get_connection() as conn:
        row = conn.execute(
            "SELECT data_json FROM processes WHERE id = ?",
            (process_id,),
        ).fetchone()
        if not row:
            print("El proceso no existe.\n")
            return
        data = json.loads(row[0])
        old_status = data.get(status_field["name"], "")
        options = status_field.get("options") or []
        hint = f" (opciones: {', '.join(options)})" if options else ""
        new_status = prompt(f"Nuevo estado{hint}")
        if not new_status:
            print("El estado es obligatorio.\n")
            return
        if options and new_status not in options:
            print("Estado inválido.\n")
            return
        data[status_field["name"]] = new_status
        conn.execute(
            "UPDATE processes SET data_json = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), process_id),
        )
        conn.execute(
            """
            INSERT INTO status_history (process_id, old_status, new_status, changed_at, changed_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                process_id,
                old_status,
                new_status,
                datetime.now().isoformat(timespec="seconds"),
                user["username"],
            ),
        )
    print("Estado actualizado y registrado en historial.\n")


def view_status_history():
    list_processes()
    process_id = prompt("ID del proceso")
    if not process_id.isdigit():
        print("ID inválido.\n")
        return
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT old_status, new_status, changed_at, changed_by
            FROM status_history
            WHERE process_id = ?
            ORDER BY changed_at DESC
            """,
            (process_id,),
        ).fetchall()
    if not rows:
        print("No hay historial de estados para este proceso.\n")
        return
    print("\n--- Historial de estados ---")
    for old_status, new_status, changed_at, changed_by in rows:
        print(f"{changed_at} | {old_status or '-'} -> {new_status} | {changed_by}")
    print()


def add_deadline(user):
    list_processes()
    process_id = prompt("ID del proceso para el vencimiento")
    due_date = prompt("Fecha de vencimiento (AAAA-MM-DD)")
    description = prompt("Descripción del vencimiento")
    if not process_id.isdigit():
        print("ID inválido.\n")
        return
    try:
        datetime.strptime(due_date, "%Y-%m-%d")
    except ValueError:
        print("Fecha inválida.\n")
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
            INSERT INTO deadlines (process_id, due_date, description, created_at, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (process_id, due_date, description, created_at, user["username"]),
        )
    print("Vencimiento registrado.\n")


def list_deadlines(include_completed=False, days_ahead=None):
    with get_connection() as conn:
        query = """
            SELECT id, process_id, due_date, description, created_at, created_by, is_completed
            FROM deadlines
        """
        params = []
        if not include_completed:
            query += " WHERE is_completed = 0"
        if days_ahead is not None:
            condition = " AND " if "WHERE" in query else " WHERE "
            query += f"{condition}date(due_date) <= date('now', ?)"
            params.append(f"+{days_ahead} days")
        query += " ORDER BY due_date ASC"
        rows = conn.execute(query, params).fetchall()
    if not rows:
        print("No hay vencimientos pendientes.\n")
        return []
    print("\n--- Vencimientos ---")
    for deadline_id, process_id, due_date, description, created_at, created_by, is_completed in rows:
        status = "completado" if is_completed else "pendiente"
        print(
            f"[{deadline_id}] Proceso {process_id} | {due_date} | {description} "
            f"| {created_by} | {status}"
        )
    print()
    return rows


def complete_deadline(user):
    rows = list_deadlines(include_completed=False)
    if not rows:
        return
    deadline_id = prompt("ID del vencimiento a marcar como completado")
    if not deadline_id.isdigit():
        print("ID inválido.\n")
        return
    with get_connection() as conn:
        updated = conn.execute(
            """
            UPDATE deadlines
            SET is_completed = 1, completed_at = ?, completed_by = ?
            WHERE id = ?
            """,
            (datetime.now().isoformat(timespec="seconds"), user["username"], deadline_id),
        )
    if updated.rowcount == 0:
        print("Vencimiento no encontrado.\n")
    else:
        print("Vencimiento marcado como completado.\n")


def deadlines_menu(user):
    print("\n--- Vencimientos y alertas ---")
    print("1. Registrar vencimiento")
    print("2. Ver vencimientos próximos (7 días)")
    print("3. Ver todos los vencimientos pendientes")
    print("4. Marcar vencimiento como completado")
    choice = prompt("Selecciona una opción")
    if choice == "1":
        add_deadline(user)
    elif choice == "2":
        list_deadlines(include_completed=False, days_ahead=7)
    elif choice == "3":
        list_deadlines(include_completed=False)
    elif choice == "4":
        complete_deadline(user)
    else:
        print("Opción inválida.\n")


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


def export_expenses_summary():
    config = load_config()
    fields = config.get("fields", DEFAULT_FIELDS)
    field_names = [field["name"] for field in fields]
    if not field_names:
        print("No hay campos configurados para agrupar.\n")
        return
    print("\n--- Exportar gastos agrupados ---")
    for index, name in enumerate(field_names, start=1):
        print(f"{index}. {name}")
    index_raw = prompt("Selecciona el campo para agrupar")
    if not index_raw.isdigit():
        print("Número inválido.\n")
        return
    index = int(index_raw) - 1
    if index < 0 or index >= len(field_names):
        print("Número fuera de rango.\n")
        return
    field_name = field_names[index]
    EXPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = EXPORTS_DIR / f"gastos_por_{field_name}_{timestamp}.csv"

    with get_connection() as conn:
        processes = conn.execute("SELECT id, data_json FROM processes").fetchall()
        expenses = conn.execute("SELECT process_id, amount FROM expenses").fetchall()

    process_lookup = {}
    for process_id, data_json in processes:
        data = json.loads(data_json)
        process_lookup[process_id] = data.get(field_name, "Sin dato")

    summary = {}
    for process_id, amount in expenses:
        key = process_lookup.get(process_id, "Sin dato")
        summary[key] = summary.get(key, 0) + amount

    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([field_name, "Total gastos"])
        for key, total in sorted(summary.items()):
            writer.writerow([key, f"{total:.2f}"])

    print(f"Exportación CSV de gastos agrupados en: {summary_path}\n")


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
    print("3. Exportar gastos agrupados")
    choice = prompt("Selecciona una opción")
    if choice == "1":
        export_to_csv()
    elif choice == "2":
        export_to_pdf()
    elif choice == "3":
        export_expenses_summary()
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


def status_menu(user):
    print("\n--- Estados del proceso ---")
    print("1. Actualizar estado")
    print("2. Ver historial de estados")
    choice = prompt("Selecciona una opción")
    if choice == "1":
        update_process_status(user)
    elif choice == "2":
        view_status_history()
    else:
        print("Opción inválida.\n")


def parse_date_input(label):
    value = prompt(label)
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        print("Fecha inválida. Usa AAAA-MM-DD.\n")
        return None


def report_processes_by_date():
    start_date = parse_date_input("Fecha inicio (AAAA-MM-DD)")
    if not start_date:
        return
    end_date = parse_date_input("Fecha fin (AAAA-MM-DD)")
    if not end_date:
        return
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, data_json, created_at
            FROM processes
            WHERE date(created_at) BETWEEN date(?) AND date(?)
            ORDER BY created_at ASC
            """,
            (start_date.date().isoformat(), end_date.date().isoformat()),
        ).fetchall()
    if not rows:
        print("No hay procesos en ese rango.\n")
        return
    print("\n--- Procesos por rango ---")
    list_processes(rows)


def report_closed_by_month():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT strftime('%Y-%m', changed_at) AS mes, COUNT(*)
            FROM status_history
            WHERE lower(new_status) IN ('cerrado', 'finalizado', 'archivado')
            GROUP BY mes
            ORDER BY mes
            """
        ).fetchall()
    if not rows:
        print("No hay cierres registrados en el historial.\n")
        return
    print("\n--- Procesos cerrados por mes ---")
    for mes, total in rows:
        print(f"{mes}: {total}")
    print()


def reports_menu():
    print("\n--- Reportes ---")
    print("1. Procesos por rango de fechas")
    print("2. Procesos cerrados por mes (historial de estados)")
    choice = prompt("Selecciona una opción")
    if choice == "1":
        report_processes_by_date()
    elif choice == "2":
        report_closed_by_month()
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
    backup_database(auto=True)
    ensure_admin_user()
    user = None
    while not user:
        user = authenticate()

    actions = {
        "1": ("Registrar nuevo proceso", add_process),
        "2": ("Listar procesos", list_processes_menu),
        "3": ("Agregar entrada de bitácora", add_log_entry),
        "4": ("Ver bitácora de un proceso", view_log),
        "5": ("Estados del proceso", lambda: status_menu(user)),
        "6": ("Vencimientos y alertas", lambda: deadlines_menu(user)),
        "7": ("Ajustes de campos", configure_fields),
        "8": ("Gastos por proceso", lambda: expenses_menu(user)),
        "9": ("Reportes", reports_menu),
        "10": ("Exportar bitácora", export_menu),
        "11": ("Respaldo manual", backup_database),
        "12": ("Gestión de usuarios", lambda: manage_users(user)),
        "13": ("Salir", None),
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
        if choice == "13":
            print("Hasta luego.")
            break
        action[1]()


if __name__ == "__main__":
    main()
