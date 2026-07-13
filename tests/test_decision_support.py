"""Ulusal Karar Destek Merkezi — analitik, AI, PDF, RBAC."""

from datetime import datetime
from unittest.mock import patch

import pytest

from auth_utils import hash_password
from constants import ROLE_MINISTRY, ROLE_MUNICIPALITY
from extensions import db
from models import Atik, CevreselEtki, Kaynak, User
from services.decision_support import (
    build_decision_support_center,
    category_shifts,
    period_snapshot,
    risk_analysis,
)
from services.decision_support_ai import enrich_decision_support
from services.decision_support_pdf import export_decision_support_pdf


FIXED_NOW = datetime(2026, 7, 13, 12, 0, 0)


def _user(**kwargs):
    defaults = dict(
        password=hash_password("TestPass1"),
        is_completed=True,
        email_verified=True,
        role="user",
        is_admin=False,
        il="Sakarya",
        ilce="Serdivan",
    )
    defaults.update(kwargs)
    user = User(**defaults)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, email):
    client.get("/cikis", follow_redirects=True)
    client.post(
        "/giris",
        data={"email": email, "password": "TestPass1"},
        follow_redirects=True,
    )


@pytest.fixture
def ds_data(app):
    with app.app_context():
        ministry = _user(
            username="ds_min",
            email="ds_min@test.com",
            role=ROLE_MINISTRY,
            il=None,
            ilce=None,
        )
        muni = _user(
            username="ds_muni",
            email="ds_muni@test.com",
            role=ROLE_MUNICIPALITY,
        )
        citizen = _user(username="ds_cit", email="ds_cit@test.com")
        normal = _user(username="ds_normal", email="ds_normal@test.com")

        for i in range(5):
            day = FIXED_NOW.replace(day=max(1, 10 - i))
            kay = Kaynak(
                baslik=f"DS-K{i}",
                aciklama="ds",
                durum="Temiz",
                kategori="Elektronik" if i % 2 == 0 else "Plastik",
                resim="default.jpg",
                latitude=40.77,
                longitude=30.39,
                ilan_durumu="Teslim Edildi" if i < 3 else "Aktif",
                moderation_status="approved",
                user_id=citizen.id,
                tarih=day,
            )
            db.session.add(kay)
            atik = Atik(
                baslik=f"DS-A{i}",
                aciklama="ds",
                kategori="Cam",
                latitude=40.78,
                longitude=30.40,
                ilan_durumu="Aktif",
                moderation_status="approved",
                user_id=citizen.id,
                tarih=day,
            )
            db.session.add(atik)
            db.session.flush()
            db.session.add(
                CevreselEtki(
                    user_id=citizen.id,
                    atik_id=atik.id,
                    tur="atik",
                    kategori=atik.kategori,
                    co2e_kg=2 + i,
                    su_litre=1,
                    atik_kg=1.5 + i,
                    dongusel_skor=5,
                    timestamp=day,
                )
            )
        db.session.commit()
        return {
            "ministry_id": ministry.id,
            "muni_id": muni.id,
            "normal_id": normal.id,
        }


def test_period_and_category_builders(app, ds_data):
    with app.app_context():
        with patch("services.decision_support.utc_now", return_value=FIXED_NOW):
            weekly = period_snapshot("weekly", now=FIXED_NOW)
            monthly = period_snapshot("monthly", now=FIXED_NOW)
            shifts = category_shifts(days=30, now=FIXED_NOW)
        assert weekly["period"] == "weekly"
        assert "ilan" in weekly["metrics"]
        assert "change_pct" in weekly
        assert monthly["period"] == "monthly"
        assert "rising" in shifts
        assert "chart" in shifts


def test_build_center_structure(app, ds_data):
    with app.app_context():
        with patch("services.decision_support.utc_now", return_value=FIXED_NOW):
            center = build_decision_support_center(now=FIXED_NOW)
        assert "weekly_report" in center
        assert "monthly_report" in center
        assert "risk_analysis" in center
        assert "campaigns" in center
        assert "municipality_comparisons" in center
        assert "category_shifts" in center
        assert "participation_trends" in center
        assert "ministry_actions" in center
        assert center["risk_analysis"]["level"] in ("dusuk", "orta", "yuksek")
        assert len(center["campaigns"]) >= 1
        assert len(center["ministry_actions"]) >= 1


def test_enrich_ai_rules(app, ds_data):
    with app.app_context():
        with patch("services.decision_support_ai.get_client", return_value=None):
            with patch("services.decision_support.utc_now", return_value=FIXED_NOW):
                center = enrich_decision_support()
        assert center["ai_source"] == "rules"
        assert center["ai"]["overview"]
        assert center["ai"]["weekly_narrative"]
        assert center["ai"]["monthly_narrative"]


def test_pdf_export_types(app, ds_data):
    with app.app_context():
        with patch("services.decision_support_ai.get_client", return_value=None):
            with patch("services.decision_support.utc_now", return_value=FIXED_NOW):
                center = enrich_decision_support()
        for rtype in ("weekly", "monthly", "full"):
            data, filename = export_decision_support_pdf(center, report_type=rtype)
            assert rtype in filename
            assert len(data) > 40
            if filename.endswith(".pdf"):
                assert data[:4] == b"%PDF"


def test_karar_destek_rbac_and_pages(client, ds_data):
    _login(client, "ds_normal@test.com")
    assert client.get("/minister/karar-destek").status_code == 403
    assert client.get("/minister/karar-destek/pdf").status_code == 403

    _login(client, "ds_min@test.com")
    with patch("services.decision_support_ai.get_client", return_value=None):
        with patch("services.decision_support.utc_now", return_value=FIXED_NOW):
            resp = client.get("/minister/karar-destek")
    assert resp.status_code == 200
    assert b"Ulusal Karar Destek" in resp.data
    assert b"Haftal" in resp.data
    assert b"Risk" in resp.data
    assert b"Kampanya" in resp.data or b"kampanya" in resp.data

    with patch("services.decision_support_ai.get_client", return_value=None):
        with patch("services.decision_support.utc_now", return_value=FIXED_NOW):
            pdf = client.get("/minister/karar-destek/pdf?type=full")
    assert pdf.status_code == 200
    assert pdf.headers["Content-Disposition"].startswith("attachment")


def test_existing_ministry_apis_untouched(client, ds_data):
    """Mevcut API yapısı korunmalı."""
    _login(client, "ds_min@test.com")
    for path in ("/minister/kpi", "/minister/map", "/minister/statistics"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert resp.is_json
