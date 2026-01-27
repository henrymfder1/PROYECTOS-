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


def list_processes():
    config = load_config()
    fields = config.get("fields", DEFAULT_FIELDS)
    field_names = [field["name"] for field in fields]
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, data_json, created_at
            FROM processes
            ORDER BY created_at DESC
            """
        ).fetchall()

    if not rows:
        print("No hay procesos registrados.\n")
        return

    print("\n--- Procesos ---")
    for row in rows:
        process_id, data_json, created_at = row
        data = json.loads(data_json)
        columns = " | ".join([data.get(field, "-") for field in field_names])
        print(f"[{process_id}] {columns} | {created_at}")
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
    print("Campos actuales:")
    for index, field in enumerate(fields, start=1):
        required_label = "sí" if field.get("required", True) else "no"
        print(
            f"{index}. {field['name']} (tipo: {field.get('type', 'text')}, "
            f"obligatorio: {required_label})"
        )

    print("\nVamos a crear una nueva lista de campos.")
    new_fields = []
    while True:
        name = prompt("Nombre del campo (enter para terminar)")
        if not name:
            break
        field_type = prompt("Tipo (text/number/date)") or "text"
        if field_type not in FIELD_TYPES:
            print("Tipo inválido, se usará 'text'.")
            field_type = "text"
        required_raw = prompt("¿Obligatorio? (s/n)") or "s"
        required = required_raw.lower().startswith("s")
        new_fields.append({"name": name, "type": field_type, "required": required})

    if not new_fields:
        print("No se realizaron cambios.\n")
        return

    save_config({"fields": new_fields})
    print("Campos actualizados.\n")


def export_to_csv():
    config = load_config()
    fields = config.get("fields", DEFAULT_FIELDS)
    field_names = [field["name"] for field in fields]
    EXPORTS_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    processes_path = EXPORTS_DIR / f"procesos_{timestamp}.csv"
    logs_path = EXPORTS_DIR / f"bitacora_{timestamp}.csv"

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

    with processes_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ID"] + field_names + ["Fecha de creación"])
        for process_id, data_json, created_at in processes:
            data = json.loads(data_json)
            writer.writerow(
                [process_id] + [data.get(field, "") for field in field_names] + [created_at]
            )

    with logs_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ID Proceso", "Fecha", "Nota"])
        for process_id, entry_date, note in logs:
            writer.writerow([process_id, entry_date, note])

    print(f"Exportación CSV creada en: {processes_path}")
    print(f"Exportación CSV de bitácora en: {logs_path}\n")


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
        "2": ("Listar procesos", list_processes),
        "3": ("Agregar entrada de bitácora", add_log_entry),
        "4": ("Ver bitácora de un proceso", view_log),
        "5": ("Ajustes de campos", configure_fields),
        "6": ("Exportar bitácora", export_menu),
        "7": ("Gestión de usuarios", lambda: manage_users(user)),
        "8": ("Salir", None),
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
        if choice == "8":
            print("Hasta luego.")
            break
        action[1]()


if __name__ == "__main__":
    main()
