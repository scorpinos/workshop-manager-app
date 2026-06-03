import pytest
import os
import tempfile
from app import create_app
from app.db import get_db

class TestConfig:
    TESTING = True
    SECRET_KEY = 'test'
    DATABASE = None
    BACKUP_DIR = 'backups_test'

@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp()
    TestConfig.DATABASE = db_path
    app = create_app(TestConfig)
    yield app
    os.close(db_fd)
    os.unlink(db_path)

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_admin(client):
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['user'] = {'role': 'admin', 'username': 'admin'}
    return client

def test_update_status_success(auth_admin, app):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO projects (client_name, date, status, work_done) VALUES ('Test Client', '2024-01-01', 'in progress', 0)")
        project_id = db.execute("SELECT id FROM projects WHERE client_name = 'Test Client'").fetchone()['id']
        db.commit()

    resp = auth_admin.patch(f'/api/projects/{project_id}/status', json={'status': 'completed'})
    assert resp.status_code == 200
    assert resp.get_json() == {'ok': True}

    with app.app_context():
        project = get_db().execute("SELECT status, work_done FROM projects WHERE id = ?", (project_id,)).fetchone()
        assert project['status'] == 'completed'
        assert project['work_done'] == 1

def test_update_status_paid(auth_admin, app):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO projects (client_name, date, status, work_done) VALUES ('Paid Client', '2024-01-01', 'in progress', 0)")
        project_id = db.execute("SELECT id FROM projects WHERE client_name = 'Paid Client'").fetchone()['id']
        db.commit()

    resp = auth_admin.patch(f'/api/projects/{project_id}/status', json={'status': 'paid'})
    assert resp.status_code == 200

    with app.app_context():
        project = get_db().execute("SELECT status, work_done FROM projects WHERE id = ?", (project_id,)).fetchone()
        assert project['status'] == 'paid'
        assert project['work_done'] == 1

def test_update_status_invalid(auth_admin, app):
    resp = auth_admin.patch('/api/projects/1/status', json={'status': 'invalid'})
    assert resp.status_code == 400
    assert 'error' in resp.get_json()

def test_update_status_not_found(auth_admin):
    resp = auth_admin.patch('/api/projects/9999/status', json={'status': 'completed'})
    assert resp.status_code == 404
    assert resp.get_json() == {'error': 'Project not found'}
