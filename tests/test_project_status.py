import pytest
from app import create_app
from app.db import get_db, close_db
import os
import uuid

@pytest.fixture
def app():
    # Use a unique database for each test
    db_name = f"test_{uuid.uuid4().hex}.sqlite3"
    db_path = os.path.join("app/data", db_name)

    class TestConfig:
        SECRET_KEY = "test"
        DATABASE = db_path
        BACKUP_DIR = "backups/test"
        TESTING = True

    app = create_app(TestConfig)

    # In create_app, init_app(app) is called, which calls init_db()
    # init_db() calls seed_defaults(), which inserts the admin user.
    # So we don't need to insert it manually here if we use the default seed.

    yield app

    with app.app_context():
        close_db()

    # Try to delete the test database
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception:
        pass

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_client(client):
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['user'] = {'id': 1, 'username': 'admin', 'role': 'admin'}
    return client

def test_update_project_status(auth_client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO projects (client_name, final_price, status, date) VALUES (?, ?, ?, ?)",
            ("Test Client", 1000, "in progress", "2024-01-01")
        )
        db.commit()
        project_id = db.execute("SELECT id FROM projects WHERE client_name = 'Test Client'").fetchone()['id']

    # Update to completed
    response = auth_client.patch(f'/api/projects/{project_id}/status', json={'status': 'completed'})
    assert response.status_code == 200

    with app.app_context():
        db = get_db()
        project = db.execute("SELECT status, work_done FROM projects WHERE id = ?", (project_id,)).fetchone()
        assert project['status'] == 'completed'
        assert project['work_done'] == 1

    # Update to paid
    response = auth_client.patch(f'/api/projects/{project_id}/status', json={'status': 'paid'})
    assert response.status_code == 200

    with app.app_context():
        db = get_db()
        project = db.execute("SELECT status, work_done FROM projects WHERE id = ?", (project_id,)).fetchone()
        assert project['status'] == 'paid'
        assert project['work_done'] == 1

def test_stats_with_paid_status(auth_client, app):
    with app.app_context():
        db = get_db()
        # Project with status 'paid' should not be in unpaid_amount even if balance > 0
        db.execute(
            "INSERT INTO projects (client_name, final_price, status, work_done, date) VALUES (?, ?, ?, ?, ?)",
            ("Paid Project", 1000, "paid", 1, "2024-01-01")
        )
        # Project with status 'completed' but balance > 0 should be in unpaid_amount
        db.execute(
            "INSERT INTO projects (client_name, final_price, status, work_done, date) VALUES (?, ?, ?, ?, ?)",
            ("Unpaid Project", 500, "completed", 1, "2024-01-01")
        )
        db.commit()

    response = auth_client.get('/api/stats')
    assert response.status_code == 200
    data = response.get_json()

    # Unpaid amount should only include the 500 from "Unpaid Project"
    assert data['unpaid_amount'] == 500
