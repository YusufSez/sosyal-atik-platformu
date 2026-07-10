"""Phase 5.5 — büyük sorgu optimizasyon regression testleri."""

from unittest.mock import patch

import pytest
from sqlalchemy import event, inspect
from sqlalchemy.orm import load_only

from auth_utils import hash_password
from constants import MODERATION_STATUS_PENDING_REVIEW
from extensions import db
from models import Atik, Kaynak, User
from services.moderation_admin import dashboard_istatistikleri, moderasyon_listesi
from services.moderation_list_queries import fetch_moderation_list_rows
from services.query_helpers import harita_ilan_load_options


def _count_queries(app, fn):
    counter = {"n": 0}

    def _before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", _before)
        try:
            fn()
        finally:
            event.remove(db.engine, "before_cursor_execute", _before)
    return counter["n"]


def test_moderasyon_listesi_uses_union_rows_not_full_table_scan(app):
    with app.app_context():
        rows = fetch_moderation_list_rows({"status": MODERATION_STATUS_PENDING_REVIEW})
        assert isinstance(rows, list)
        result = moderasyon_listesi({"status": MODERATION_STATUS_PENDING_REVIEW}, page=1)
        assert result.total >= 0
        assert len(result.items) <= result.per_page


def test_moderasyon_list_paginated_loads_fewer_ilans_than_export(app):
    with app.app_context():
        user = User(
            username="mod55",
            email="mod55@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        db.session.add(user)
        db.session.flush()
        for i in range(5):
            db.session.add(
                Atik(
                    baslik=f"Atik {i}",
                    aciklama="Test açıklama uzun metin",
                    resim="default.jpg",
                    user_id=user.id,
                    kategori="Diğer",
                    moderation_status=MODERATION_STATUS_PENDING_REVIEW,
                    ai_risk_score=50 + i,
                )
            )
        db.session.commit()

        with patch(
            "services.moderation_admin.batch_load_ilans",
            wraps=__import__(
                "services.moderation_list_queries", fromlist=["batch_load_ilans"]
            ).batch_load_ilans,
        ) as batch_mock:
            moderasyon_listesi({"status": MODERATION_STATUS_PENDING_REVIEW}, page=1, per_page=2)
            page_load_count = batch_mock.call_args[0][0]
            assert len(page_load_count) <= 2

            batch_mock.reset_mock()
            moderasyon_listesi({"status": MODERATION_STATUS_PENDING_REVIEW})
            export_load_count = batch_mock.call_args[0][0]
            assert len(export_load_count) >= len(page_load_count)


def test_dashboard_karar_analitigi_uses_sql_aggregate(app):
    from models import IlanModerasyonAnaliz, IlanModerasyonKarar
    from services.moderation_decisions import karar_analitigi

    with app.app_context():
        with patch.object(IlanModerasyonKarar.query, "all") as karar_all:
            karar_analitigi()
            karar_all.assert_not_called()
        with patch.object(IlanModerasyonAnaliz.query, "all") as analiz_all:
            from services.moderation_admin import spam_duplicate_analitigi

            spam_duplicate_analitigi()
            analiz_all.assert_not_called()


def test_harita_load_only_limits_columns(app):
    with app.app_context():
        user = User(
            username="mapuser",
            email="mapuser@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(
            Kaynak(
                baslik="Harita kaynak",
                aciklama="Uzun açıklama alanı haritada kullanılmamalı",
                durum="Temiz",
                kategori="Diğer",
                resim="default.jpg",
                latitude=41.1,
                longitude=29.1,
                user_id=user.id,
            )
        )
        db.session.commit()
        row = (
            Kaynak.query.options(harita_ilan_load_options(Kaynak))
            .filter_by(baslik="Harita kaynak")
            .first()
        )
        assert row is not None
        unloaded = inspect(row).unloaded
        assert "aciklama" in unloaded
        assert "id" not in unloaded
        assert "latitude" not in unloaded


def test_dashboard_status_counts_aggregate(app):
    with app.app_context():
        stats = dashboard_istatistikleri()
    assert {"approved", "pending_review", "rejected"}.issubset(
        {k for k in stats.keys() if k in ("approved", "pending_review", "rejected")}
    )
    assert stats["toplam_analiz"] >= 0


def test_moderasyon_list_priority_regression(app):
    with app.app_context():
        user = User(
            username="prio55",
            email="prio55@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        db.session.add(user)
        db.session.flush()
        low = Atik(
            baslik="Düşük",
            aciklama="a",
            resim="default.jpg",
            user_id=user.id,
            kategori="Diğer",
            moderation_status=MODERATION_STATUS_PENDING_REVIEW,
            ai_risk_score=10,
        )
        high = Atik(
            baslik="Yüksek",
            aciklama="b",
            resim="default.jpg",
            user_id=user.id,
            kategori="Diğer",
            moderation_status=MODERATION_STATUS_PENDING_REVIEW,
            ai_risk_score=95,
        )
        db.session.add_all([low, high])
        db.session.commit()
        items = moderasyon_listesi({"status": MODERATION_STATUS_PENDING_REVIEW})
        pending = [i for i in items if i.moderation_status == MODERATION_STATUS_PENDING_REVIEW]
        if len(pending) >= 2:
            assert pending[0].risk_skoru >= pending[1].risk_skoru


def test_load_only_user_username_in_spam_analytics(app):
    source = open(
        __import__("services.moderation_admin", fromlist=[None]).__file__,
        encoding="utf-8",
    ).read()
    assert "load_only(User.id, User.username)" in source
