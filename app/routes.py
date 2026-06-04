from functools import wraps

from flask import Blueprint, Response, jsonify, request, session
from werkzeug.security import generate_password_hash

from .db import get_db
from .formula_engine import FormulaError, calculate_materials
from .services import create_backup, export_projects, get_project, list_projects, save_project, stats

bp = Blueprint("api", __name__)


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Login required"}), 401
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user", {}).get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return view(*args, **kwargs)

    return wrapped


@bp.errorhandler(ValueError)
def value_error(error):
    return jsonify({"error": str(error)}), 400


@bp.errorhandler(FormulaError)
def formula_error(error):
    return jsonify({"error": str(error)}), 400


@bp.get("/me")
@api_login_required
def me():
    return jsonify(session.get("user", {}))


@bp.get("/projects")
@api_login_required
def projects():
    return jsonify(list_projects(request.args))


@bp.post("/projects")
@api_login_required
@admin_required
def create_project():
    return jsonify(save_project(request.get_json() or {}, session.get("user_id")))


@bp.get("/projects/<int:project_id>")
@api_login_required
def project_detail(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project)


@bp.put("/projects/<int:project_id>")
@api_login_required
@admin_required
def update_project(project_id):
    return jsonify(save_project(request.get_json() or {}, session.get("user_id"), project_id))


@bp.patch("/projects/<int:project_id>/work-done")
@api_login_required
@admin_required
def update_project_work_done(project_id):
    payload = request.get_json() or {}
    work_done = 1 if payload.get("work_done") else 0
    get_db().execute(
        "UPDATE projects SET work_done = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (work_done, "completed" if work_done else "in progress", project_id),
    )
    get_db().commit()
    return jsonify({"ok": True})


@bp.patch("/projects/<int:project_id>/status")
@api_login_required
@admin_required
def update_project_status(project_id):
    payload = request.get_json() or {}
    status = payload.get("status")
    valid_statuses = ("in progress", "completed", "paid")
    if status not in valid_statuses:
        return jsonify({"error": f"Invalid status: {status}. Must be one of {valid_statuses}"}), 400

    db = get_db()
    # Check if project exists
    project = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not project:
        return jsonify({"error": "Project not found"}), 404

    work_done = 1 if status in ("completed", "paid") else 0
    db.execute(
        "UPDATE projects SET status = ?, work_done = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, work_done, project_id),
    )
    db.commit()
    return jsonify({"ok": True})


@bp.delete("/projects/<int:project_id>")
@api_login_required
@admin_required
def delete_project(project_id):
    get_db().execute("DELETE FROM projects WHERE id = ?", (project_id,))
    get_db().commit()
    return jsonify({"ok": True})


@bp.post("/calculate")
@api_login_required
def calculate():
    payload = request.get_json() or {}
    materials = calculate_materials(payload.get("width") or 0, payload.get("height") or 0, payload.get("materials") or [])
    total = round(sum(item["total_price"] for item in materials if not item.get("is_labor")), 2)
    labor_total = round(sum(item["total_price"] for item in materials if item.get("is_labor")), 2)
    final_price = float(payload.get("final_price") or 0)
    profit = final_price - total - labor_total
    return jsonify(
        {
            "materials": materials,
            "totals": {
                "materials_total": total,
                "labor_total": labor_total,
                "price": round(total * 2, 2),
                "final_price": final_price,
                "profit": round(profit, 2),
                "profit_percent": round((profit / final_price) * 100, 1) if final_price else 0,
            },
        }
    )


@bp.get("/lookups")
@api_login_required
def lookups():
    db = get_db()
    payload = {}
    for table in ["clients", "shops", "contractors", "project_types", "categories", "materials", "units"]:
        payload[table] = db.execute(f"SELECT * FROM {table} ORDER BY name").fetchall()
    return jsonify(payload)


@bp.get("/templates/<project_type>")
@api_login_required
def templates(project_type):
    rows = get_db().execute("SELECT * FROM material_templates WHERE project_type = ? ORDER BY material_name", (project_type,)).fetchall()
    return jsonify(rows)


@bp.post("/materials")
@api_login_required
@admin_required
def create_material():
    payload = request.get_json() or {}
    name = payload.get("name", "").strip()
    if not name:
        raise ValueError("Material name is required")
    existing = get_db().execute("SELECT id FROM materials WHERE lower(name) = lower(?) AND unit = ?", (name, payload.get("unit", "Pcs"))).fetchone()
    if existing:
        raise ValueError("A material with this name and unit already exists")
    get_db().execute(
        """
        INSERT INTO materials (name, category, unit, unit_price, formula, waste_percent)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            payload.get("category", ""),
            payload.get("unit", "Pcs"),
            payload.get("unit_price") or payload.get("price") or 0,
            payload.get("formula", ""),
            payload.get("waste_percent") or 0,
        ),
    )
    get_db().commit()
    return jsonify({"ok": True})


@bp.put("/materials/<int:material_id>")
@api_login_required
@admin_required
def update_material(material_id):
    payload = request.get_json() or {}
    name = payload.get("name", "").strip()
    if not name:
        raise ValueError("Material name is required")
    cursor = get_db().execute(
        """
        UPDATE materials
        SET name = ?, category = ?, unit = ?, unit_price = ?, formula = ?, waste_percent = ?
        WHERE id = ?
        """,
        (
            name,
            payload.get("category", ""),
            payload.get("unit", "Pcs"),
            payload.get("unit_price") or payload.get("price") or 0,
            payload.get("formula", ""),
            payload.get("waste_percent") or 0,
            material_id,
        ),
    )
    if cursor.rowcount == 0:
        return jsonify({"error": "Material not found"}), 404
    get_db().commit()
    return jsonify({"ok": True})


@bp.delete("/materials/<int:material_id>")
@api_login_required
@admin_required
def delete_material(material_id):
    get_db().execute("DELETE FROM materials WHERE id = ?", (material_id,))
    get_db().commit()
    return jsonify({"ok": True})


@bp.get("/users")
@api_login_required
@admin_required
def users():
    return jsonify(get_db().execute("SELECT id, username, role, display_name, created_at FROM users ORDER BY username").fetchall())


@bp.post("/payments")
@api_login_required
@admin_required
def add_payment():
    payload = request.get_json() or {}
    if not payload.get("project_id"):
        raise ValueError("Project is required")
    get_db().execute(
        "INSERT INTO payments (project_id, amount, payment_date, note) VALUES (?, ?, ?, ?)",
        (payload["project_id"], payload.get("amount") or 0, payload.get("payment_date"), payload.get("note", "")),
    )
    get_db().commit()
    return jsonify(get_project(payload["project_id"]))


@bp.get("/stats")
@api_login_required
def statistics():
    return jsonify(stats(request.args))


@bp.get("/export/<fmt>")
@api_login_required
def export(fmt):
    if fmt not in {"csv", "xlsx", "pdf"}:
        return jsonify({"error": "Unsupported export format"}), 400
    data, mimetype, filename = export_projects(fmt)
    return Response(data, mimetype=mimetype, headers={"Content-Disposition": f"attachment; filename={filename}"})


@bp.post("/backup")
@api_login_required
@admin_required
def backup():
    path = create_backup()
    return jsonify({"ok": True, "path": str(path)})


@bp.post("/users")
@api_login_required
@admin_required
def create_user():
    payload = request.get_json() or {}
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    role = payload.get("role", "worker")
    if not username or not password:
        raise ValueError("Username and password are required")
    get_db().execute(
        "INSERT INTO users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)",
        (username, generate_password_hash(password), role, payload.get("display_name", username)),
    )
    get_db().commit()
    return jsonify({"ok": True})


@bp.put("/users/<int:user_id>")
@api_login_required
@admin_required
def update_user(user_id):
    payload = request.get_json() or {}
    role = payload.get("role", "worker")
    display_name = payload.get("display_name", "")
    password = payload.get("password", "")
    if password:
        get_db().execute(
            "UPDATE users SET role = ?, display_name = ?, password_hash = ? WHERE id = ?",
            (role, display_name, generate_password_hash(password), user_id),
        )
    else:
        get_db().execute("UPDATE users SET role = ?, display_name = ? WHERE id = ?", (role, display_name, user_id))
    get_db().commit()
    return jsonify({"ok": True})
