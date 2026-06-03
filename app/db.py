import sqlite3
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash


def dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_db():
    if "db" not in g:
        Path(current_app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = dict_factory
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    schema_path = Path(__file__).with_name("schema.sql")
    db.execute("PRAGMA foreign_keys = OFF")
    db.executescript(schema_path.read_text(encoding="utf-8"))
    migrate_db(db)
    seed_defaults(db)
    db.commit()
    db.execute("PRAGMA foreign_keys = ON")


def seed_defaults(db):
    db.execute(
        """
        INSERT OR IGNORE INTO users (username, password_hash, role, display_name)
        VALUES (?, ?, ?, ?)
        """,
        ("admin", generate_password_hash("admin123"), "admin", "Administrator"),
    )
    for name in ["Glass", "Wood", "Metal", "Fabric", "Labor", "Hardware", "Other"]:
        db.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
    db.execute("DELETE FROM units WHERE name = 'Kg'")
    for unit in ["Pcs", "M", "M²", "sheet", "Other"]:
        db.execute("INSERT OR IGNORE INTO units (name) VALUES (?)", (unit,))


def migrate_db(db):
    tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    if "materials_old" in tables and "materials" in tables:
        db.execute(
            """
            INSERT OR IGNORE INTO materials
            (id, name, category, unit, unit_price, formula, waste_percent, created_at)
            SELECT id, name, category, unit, unit_price, formula, waste_percent, created_at
            FROM materials_old
            """
        )
        rebuild_project_materials(db)
        rebuild_material_templates(db)
        db.execute("DROP TABLE IF EXISTS materials_old")

    def columns(table):
        return {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}

    project_cols = columns("projects")
    if "address" not in project_cols:
        db.execute("ALTER TABLE projects ADD COLUMN address TEXT")
    if "work_done" not in project_cols:
        db.execute("ALTER TABLE projects ADD COLUMN work_done INTEGER NOT NULL DEFAULT 0")

    material_cols = columns("project_materials")
    if "is_labor" not in material_cols:
        db.execute("ALTER TABLE project_materials ADD COLUMN is_labor INTEGER NOT NULL DEFAULT 0")

    material_indexes = db.execute("PRAGMA index_list(materials)").fetchall()
    has_name_only_unique = False
    for index in material_indexes:
        if not index.get("unique"):
            continue
        cols = [row["name"] for row in db.execute(f"PRAGMA index_info({index['name']})").fetchall()]
        if cols == ["name"]:
            has_name_only_unique = True
    if has_name_only_unique:
        db.execute("ALTER TABLE materials RENAME TO materials_old")
        db.execute(
            """
            CREATE TABLE materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                unit TEXT NOT NULL,
                unit_price REAL NOT NULL DEFAULT 0,
                formula TEXT,
                waste_percent REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, unit)
            )
            """
        )
        db.execute(
            """
            INSERT OR IGNORE INTO materials
            (id, name, category, unit, unit_price, formula, waste_percent, created_at)
            SELECT id, name, category, unit, unit_price, formula, waste_percent, created_at
            FROM materials_old
            """
        )
        rebuild_project_materials(db)
        rebuild_material_templates(db)
        db.execute("DROP TABLE materials_old")

    template_fks = db.execute("PRAGMA foreign_key_list(material_templates)").fetchall()
    if any(row["table"] == "materials_old" for row in template_fks):
        rebuild_material_templates(db)


def rebuild_project_materials(db):
    db.execute("ALTER TABLE project_materials RENAME TO project_materials_old")
    db.execute(
        """
        CREATE TABLE project_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            material_id INTEGER,
            material_name TEXT NOT NULL,
            category TEXT,
            unit TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            unit_price REAL NOT NULL DEFAULT 0,
            formula TEXT,
            auto_formula INTEGER NOT NULL DEFAULT 0,
            manual_override INTEGER NOT NULL DEFAULT 0,
            waste_percent REAL NOT NULL DEFAULT 0,
            is_labor INTEGER NOT NULL DEFAULT 0,
            total_price REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
        """
    )
    old_cols = {row["name"] for row in db.execute("PRAGMA table_info(project_materials_old)").fetchall()}
    is_labor_expr = "is_labor" if "is_labor" in old_cols else "0"
    db.execute(
        f"""
        INSERT INTO project_materials
        (id, project_id, material_id, material_name, category, unit, quantity, unit_price, formula,
         auto_formula, manual_override, waste_percent, is_labor, total_price)
        SELECT id, project_id, material_id, material_name, category, unit, quantity, unit_price, formula,
               auto_formula, manual_override, waste_percent, {is_labor_expr}, total_price
        FROM project_materials_old
        """
    )
    db.execute("DROP TABLE project_materials_old")
    db.execute("CREATE INDEX IF NOT EXISTS idx_project_materials_project ON project_materials(project_id)")


def rebuild_material_templates(db):
    db.execute("ALTER TABLE material_templates RENAME TO material_templates_old")
    db.execute(
        """
        CREATE TABLE material_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_type TEXT NOT NULL,
            material_id INTEGER,
            material_name TEXT NOT NULL,
            category TEXT,
            unit TEXT NOT NULL,
            unit_price REAL NOT NULL DEFAULT 0,
            formula TEXT,
            auto_formula INTEGER NOT NULL DEFAULT 0,
            waste_percent REAL NOT NULL DEFAULT 0,
            UNIQUE(project_type, material_name),
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
        """
    )
    db.execute(
        """
        INSERT OR IGNORE INTO material_templates
        (id, project_type, material_id, material_name, category, unit, unit_price, formula, auto_formula, waste_percent)
        SELECT id, project_type, material_id, material_name, category, unit, unit_price, formula, auto_formula, waste_percent
        FROM material_templates_old
        """
    )
    db.execute("DROP TABLE material_templates_old")


def init_app(app):
    with app.app_context():
        init_db()
