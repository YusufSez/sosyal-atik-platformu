"""Demo Manager — ayarlar, öncelik, yetki ve toggle testleri."""

from auth_utils import hash_password
from extensions import db
from models import AdminAuditLog, User
from services.demo_manager import (
    DEMO_AI_KEY,
    DEMO_DASHBOARD_KEY,
    DEMO_MODE_KEY,
    DEMO_PREDICTION_KEY,
    get_stored_demo_settings,
    is_demo_mode,
    save_demo_settings,
    should_use_demo,
    use_demo_ai,
    use_demo_dashboard,
    use_demo_prediction,
)


def _make_user(**kwargs):
    defaults = {
        "password": hash_password("TestPass1"),
        "is_completed": True,
        "email_verified": True,
        "role": "user",
        "is_admin": False,
    }
    defaults.update(kwargs)
    user = User(**defaults)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, email, password="TestPass1"):
    return client.post(
        "/giris",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


# --- Demo Manager birim testleri ---


def test_env_demo_mode_when_no_db_setting(app, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    app.config["DEMO_MODE"] = True
    with app.app_context():
        assert is_demo_mode() is True
        assert use_demo_dashboard() is True
        assert use_demo_prediction() is True
        assert use_demo_ai() is True


def test_admin_setting_overrides_env(app, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    app.config["DEMO_MODE"] = True
    with app.app_context():
        admin = _make_user(
            username="demo_sa",
            email="demo_sa@test.com",
            role="superadmin",
            is_admin=True,
        )
        save_demo_settings({DEMO_MODE_KEY: False}, admin_id=admin.id, log_changes=False)
        assert is_demo_mode() is False
        assert use_demo_dashboard() is False


def test_should_use_demo_decision_order(app):
    with app.app_context():
        admin = _make_user(
            username="dm1",
            email="dm1@test.com",
            role="admin",
            is_admin=True,
        )
        # Master off, feature off → never demo
        save_demo_settings(
            {
                DEMO_MODE_KEY: False,
                DEMO_DASHBOARD_KEY: False,
                DEMO_PREDICTION_KEY: False,
                DEMO_AI_KEY: False,
            },
            admin_id=admin.id,
            log_changes=False,
        )
        assert should_use_demo("dashboard", real_data_sufficient=False) is False
        assert should_use_demo("dashboard", real_data_sufficient=True) is False

        # Master off, feature on, insufficient → demo
        save_demo_settings(
            {DEMO_DASHBOARD_KEY: True},
            admin_id=admin.id,
            log_changes=False,
        )
        assert should_use_demo("dashboard", real_data_sufficient=False) is True
        assert should_use_demo("dashboard", real_data_sufficient=True) is False

        # Master on → always demo
        save_demo_settings({DEMO_MODE_KEY: True}, admin_id=admin.id, log_changes=False)
        assert should_use_demo("dashboard", real_data_sufficient=True) is True
        assert should_use_demo("prediction", real_data_sufficient=True) is True


def test_save_demo_settings_writes_audit_log(app):
    with app.app_context():
        admin = _make_user(
            username="dm_audit",
            email="dm_audit@test.com",
            role="admin",
            is_admin=True,
        )
        logged = save_demo_settings(
            {DEMO_MODE_KEY: True, DEMO_PREDICTION_KEY: True},
            admin_id=admin.id,
        )
        assert "Demo Mode Enabled" in logged
        assert "Demo Prediction Enabled" in logged
        assert AdminAuditLog.query.filter_by(action="Demo Mode Enabled").count() == 1

        logged2 = save_demo_settings(
            {DEMO_PREDICTION_KEY: False},
            admin_id=admin.id,
        )
        assert "Demo Prediction Disabled" in logged2
        assert AdminAuditLog.query.filter_by(action="Demo Prediction Disabled").count() == 1


def test_settings_persist_across_reads(app):
    with app.app_context():
        admin = _make_user(
            username="dm_persist",
            email="dm_persist@test.com",
            role="admin",
            is_admin=True,
        )
        save_demo_settings(
            {DEMO_MODE_KEY: True, DEMO_AI_KEY: True},
            admin_id=admin.id,
            log_changes=False,
        )
        stored = get_stored_demo_settings()
        assert stored[DEMO_MODE_KEY] is True
        assert stored[DEMO_AI_KEY] is True
        assert is_demo_mode() is True


# --- Admin yetki / HTTP toggle ---


def test_admin_settings_forbidden_for_normal_user(client, app):
    with app.app_context():
        _make_user(username="norm", email="norm_demo@test.com")
    _login(client, "norm_demo@test.com")
    assert client.get("/admin/settings").status_code == 403
    assert client.post("/admin/settings", data={"demo_mode": "1"}).status_code == 403


def test_admin_can_toggle_demo_settings(client, app):
    with app.app_context():
        _make_user(
            username="adm_demo",
            email="adm_demo@test.com",
            role="admin",
            is_admin=True,
        )
    _login(client, "adm_demo@test.com")
    resp = client.get("/admin/settings")
    assert resp.status_code == 200
    assert b"Demo Y" in resp.data or "Demo Yönetimi".encode("utf-8") in resp.data

    resp = client.post(
        "/admin/settings",
        data={
            "demo_mode": "1",
            "demo_ai": "1",
            "demo_dashboard": "1",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        assert is_demo_mode() is True
        assert use_demo_ai() is True
        assert use_demo_dashboard() is True
        assert AdminAuditLog.query.filter_by(action="Demo Mode Enabled").count() >= 1


def test_superadmin_can_toggle_demo_settings(client, app):
    with app.app_context():
        _make_user(
            username="sa_demo",
            email="sa_demo@test.com",
            role="superadmin",
            is_admin=True,
        )
    _login(client, "sa_demo@test.com")
    resp = client.post(
        "/admin/settings",
        data={"demo_prediction": "1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        assert get_stored_demo_settings()[DEMO_PREDICTION_KEY] is True


def test_demo_banner_only_for_admins(client, app):
    with app.app_context():
        admin = _make_user(
            username="adm_ban",
            email="adm_ban@test.com",
            role="admin",
            is_admin=True,
        )
        _make_user(username="user_ban", email="user_ban@test.com")
        save_demo_settings({DEMO_MODE_KEY: True}, admin_id=admin.id, log_changes=False)

    _login(client, "adm_ban@test.com")
    home = client.get("/")
    assert home.status_code == 200
    assert "Demo Modu Aktif".encode("utf-8") in home.data

    client.get("/cikis", follow_redirects=True)
    _login(client, "user_ban@test.com")
    home2 = client.get("/")
    assert "Demo Modu Aktif".encode("utf-8") not in home2.data


def test_dashboard_uses_demo_when_mode_on(app):
    from services.municipality_analytics import municipality_dashboard

    with app.app_context():
        admin = _make_user(
            username="dm_dash",
            email="dm_dash@test.com",
            role="admin",
            is_admin=True,
        )
        save_demo_settings({DEMO_MODE_KEY: True}, admin_id=admin.id, log_changes=False)
        data = municipality_dashboard(il="Sakarya")
        assert data["toplam_aktif_ilan"] == 3200
        assert data["teslim_orani"] == 82.0
        assert data["co2e_kg"] == 25000.0
