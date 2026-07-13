"""AI Prediction Engine — istatistiksel tahmin + AI yorum testleri."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from auth_utils import hash_password
from constants import ROLE_MUNICIPALITY, ROLE_MINISTRY
from extensions import db
from models import Atik, CevreselEtki, Kaynak, User
from services.prediction_ai import generate_prediction_report
from services.prediction_engine import (
    FORECAST_HORIZONS_DAYS,
    LOOKBACK_MONTHS,
    METRIC_KEYS,
    _linear_regression,
    _predict_next_value,
    run_multi_lookback_forecast,
    run_statistical_forecast,
)


FIXED_NOW = datetime(2026, 7, 1, 12, 0, 0)


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
    client.post(
        "/giris",
        data={"email": email, "password": "TestPass1"},
        follow_redirects=True,
    )


@pytest.fixture
def prediction_data(app):
    with app.app_context():
        muni = _user(
            username="pred_muni",
            email="pred_muni@test.com",
            role=ROLE_MUNICIPALITY,
        )
        ministry = _user(
            username="pred_min",
            email="pred_min@test.com",
            role=ROLE_MINISTRY,
            il=None,
            ilce=None,
        )
        citizen = _user(username="pred_cit", email="pred_cit@test.com")
        normal = _user(username="pred_normal", email="pred_normal@test.com")

        # 14 aylık artan seri
        for i in range(14):
            month_dt = FIXED_NOW.replace(day=15) - timedelta(days=30 * (13 - i))
            for _ in range(i + 1):
                kay = Kaynak(
                    baslik=f"K{i}",
                    aciklama="pred",
                    durum="Temiz",
                    kategori="Elektronik",
                    resim="default.jpg",
                    latitude=40.77,
                    longitude=30.39,
                    ilan_durumu="Teslim Edildi" if i % 2 == 0 else "Aktif",
                    moderation_status="approved",
                    user_id=citizen.id,
                    tarih=month_dt,
                )
                db.session.add(kay)
            atik = Atik(
                baslik=f"A{i}",
                aciklama="pred",
                kategori="Elektronik Atık" if i > 7 else "Plastik",
                latitude=40.78,
                longitude=30.40,
                ilan_durumu="Aktif",
                moderation_status="approved",
                user_id=citizen.id,
                tarih=month_dt,
            )
            db.session.add(atik)
            db.session.flush()
            db.session.add(
                CevreselEtki(
                    user_id=citizen.id,
                    atik_id=atik.id,
                    tur="atik",
                    kategori=atik.kategori,
                    co2e_kg=3 + i,
                    su_litre=0,
                    atik_kg=2.0 + i * 0.5,
                    dongusel_skor=10,
                    timestamp=month_dt,
                )
            )
        db.session.commit()
        return {
            "muni_id": muni.id,
            "ministry_id": ministry.id,
            "normal_id": normal.id,
        }


# --- Unit: math ---


def test_linear_regression_increasing():
    intercept, slope = _linear_regression([1, 2, 3, 4, 5])
    assert slope == pytest.approx(1.0, abs=0.01)
    pred = _predict_next_value([1, 2, 3, 4, 5], steps_ahead=1)
    assert pred == pytest.approx(6.0, abs=0.1)


def test_linear_regression_empty_and_single():
    assert _predict_next_value([], 1) == 0.0
    assert _predict_next_value([10], 1) == pytest.approx(10.0)


# --- Statistical engine ---


def test_statistical_forecast_structure(app, prediction_data):
    with app.app_context():
        with patch("services.prediction_engine.utc_now", return_value=FIXED_NOW):
            result = run_statistical_forecast(12, il="Sakarya", now=FIXED_NOW)

        assert result["lookback_months"] == 12
        assert result["engine"] == "ols-trend"
        assert len(result["history"]) == 12
        assert set(result["horizons_days"]) == {7, 30, 90, 180, 365}
        for days in FORECAST_HORIZONS_DAYS:
            block = result["forecasts"][str(days)]
            for key in METRIC_KEYS:
                assert key in block
                m = block[key]
                assert m["predicted"] is not None
                assert "confidence_pct" in m
                assert "confidence_interval" in m
                assert m["trend"] in ("yukselis", "dusus", "stabil")
                assert m["risk"] in ("dusuk", "orta", "yuksek")
            assert 0 <= block["teslim_orani"]["predicted"] <= 100
            assert 0 <= block["katilim"]["predicted"] <= 100
            assert block["atik_miktari"]["predicted"] >= 0
            assert block["co2"]["predicted"] >= 0
        assert "labels" in result["chart"]
        assert "forecast_atik" in result["chart"]
        assert "forecast_co2" in result["chart"]
        assert "forecast_katilim" in result["chart"]
        assert len(result["chart"]["horizon_labels"]) == 5


def test_multi_lookback(app, prediction_data):
    with app.app_context():
        multi = run_multi_lookback_forecast(il="Sakarya", now=FIXED_NOW)
        for m in LOOKBACK_MONTHS:
            assert str(m) in multi["lookbacks"]
        assert multi["primary"]["lookback_months"] == 12
        assert multi["horizons_days"] == list(FORECAST_HORIZONS_DAYS)


def test_forecast_detects_growth_trend(app, prediction_data):
    with app.app_context():
        result = run_statistical_forecast(12, il="Sakarya", now=FIXED_NOW)
        kaynak_30 = result["forecasts"]["30"]["kaynak_paylasimi"]
        assert kaynak_30["predicted"] > 0
        assert kaynak_30["change_pct"] >= 0


def test_top_category_prediction(app, prediction_data):
    with app.app_context():
        result = run_statistical_forecast(12, il="Sakarya", now=FIXED_NOW)
        kat = result["forecasts"]["30"]["kategori_artisi"]
        assert kat["kategori"] in (
            "Elektronik",
            "Plastik",
            "Diğer",
            "Cam",
            "Metal",
            "Organik",
            "Bitkisel Yağ",
        )
        assert "confidence_pct" in kat
        alias = result["forecasts"]["30"]["en_yogun_kategori"]
        assert alias["en_yogun_kategori"]


# --- AI narratives ---


def test_prediction_report_rule_based(app, prediction_data):
    with app.app_context():
        with patch("services.prediction_ai.get_client", return_value=None):
            with patch("services.prediction_engine.utc_now", return_value=FIXED_NOW):
                report = generate_prediction_report(
                    12, il="Sakarya", include_all_lookbacks=True
                )
        assert report["narrative_source"] == "rules"
        assert len(report["narratives"]) >= 1
        primary = report["primary"]
        sample = primary["forecasts"]["30"]["atik_miktari"]
        assert sample["ai_yorum"]
        assert "güven" in sample["ai_yorum"].lower() or "Güven" in sample["ai_yorum"] or "%" in sample["ai_yorum"]
        assert "primary" in report
        assert "lookbacks" in report


# --- API / RBAC ---


def test_belediye_predictions_api(client, prediction_data):
    _login(client, "pred_muni@test.com")
    with patch("services.prediction_ai.get_client", return_value=None):
        with patch("services.prediction_engine.utc_now", return_value=FIXED_NOW):
            resp = client.get("/belediye/api/predictions?il=Sakarya&lookback=12")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "narratives" in data
    assert "primary" in data
    f30 = data["primary"]["forecasts"]["30"]
    assert f30["atik_miktari"]["predicted"] >= 0
    assert "katilim" in f30
    assert "co2" in f30
    assert "180" in data["primary"]["forecasts"]
    assert "365" in data["primary"]["forecasts"]


def test_minister_predictions_api(client, prediction_data):
    _login(client, "pred_min@test.com")
    with patch("services.prediction_ai.get_client", return_value=None):
        with patch("services.prediction_engine.utc_now", return_value=FIXED_NOW):
            resp = client.get("/minister/predictions?lookback=12")
    assert resp.status_code == 200
    assert "forecasts" in resp.get_json()["primary"]


def test_predictions_api_forbidden(client, prediction_data):
    _login(client, "pred_normal@test.com")
    assert client.get("/belediye/api/predictions").status_code == 403
    assert client.get("/minister/predictions").status_code == 403


def test_dashboard_includes_prediction_panel(client, prediction_data):
    _login(client, "pred_muni@test.com")
    resp = client.get("/belediye/dashboard")
    assert resp.status_code == 200
    assert b"AI Prediction Engine" in resp.data
    assert b"prediction-panel-config" in resp.data

    client.get("/cikis", follow_redirects=True)
    _login(client, "pred_min@test.com")
    resp = client.get("/minister/dashboard")
    assert resp.status_code == 200
    assert b"AI Prediction Engine" in resp.data
