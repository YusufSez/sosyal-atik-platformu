"""Moderasyon listesi — SQL UNION + öncelik sıralaması (bellek dostu)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import literal, select
from sqlalchemy.orm import joinedload, load_only, selectinload

from constants import MODERATION_LISTE_BRANCH_LIMIT
from extensions import db
from models import Atik, IlanModerasyonAnaliz, Kaynak, User
from services.moderation_priority import sort_moderation_items


@dataclass
class ModerasyonListeSatir:
    tur: str
    ilan_id: int
    moderation_status: str
    ai_risk_score: int | None
    tarih: datetime | None
    baslik: str
    aciklama: str | None
    user_id: int
    kategori: str | None
    alt_kategori: str | None
    resim: str | None
    final_risk: int | None
    spam_score: int | None
    duplicate_score: int | None
    category: str | None
    purpose: str | None
    confidence: float | None

    @property
    def risk_skoru(self) -> int | None:
        return self.final_risk if self.final_risk is not None else self.ai_risk_score


def _filtre_uygula_ilan(stmt, model, filters: dict):
    status = filters.get("status")
    if status:
        stmt = stmt.where(model.moderation_status == status)
    risk_min = filters.get("risk_min")
    if risk_min:
        stmt = stmt.where(model.ai_risk_score >= int(risk_min))
    kategori = filters.get("kategori")
    if kategori:
        stmt = stmt.where(model.kategori == kategori)
    username = filters.get("username")
    if username:
        stmt = stmt.join(User, model.user_id == User.id).where(
            User.username.ilike(f"%{username}%")
        )
    date_from = filters.get("date_from")
    if date_from:
        stmt = stmt.where(model.tarih >= date_from)
    date_to = filters.get("date_to")
    if date_to:
        stmt = stmt.where(model.tarih <= date_to)
    q = filters.get("q")
    if q:
        from sqlalchemy import or_

        stmt = stmt.where(
            or_(model.baslik.ilike(f"%{q}%"), model.aciklama.ilike(f"%{q}%"))
        )
    return stmt


def _analiz_join(model, tur: str):
    analiz = IlanModerasyonAnaliz
    if tur == "kaynak":
        return (
            analiz,
            (analiz.kaynak_id == model.id)
            & (analiz.tur == "kaynak")
            & analiz.is_current.is_(True),
        )
    return (
        analiz,
        (analiz.atik_id == model.id)
        & (analiz.tur == "atik")
        & analiz.is_current.is_(True),
    )


def _branch_stmt(model, tur: str, filters: dict):
    analiz_model, join_cond = _analiz_join(model, tur)
    durum_col = model.durum if tur == "kaynak" else literal(None)
    stmt = (
        select(
            literal(tur).label("tur"),
            model.id.label("ilan_id"),
            model.moderation_status,
            model.ai_risk_score,
            model.tarih,
            model.baslik,
            model.aciklama,
            model.user_id,
            model.kategori,
            durum_col.label("alt_kategori"),
            model.resim,
            analiz_model.final_risk,
            analiz_model.spam_score,
            analiz_model.duplicate_score,
            analiz_model.category,
            analiz_model.purpose,
            analiz_model.confidence,
        )
        .select_from(model)
        .outerjoin(analiz_model, join_cond)
    )
    return (
        _filtre_uygula_ilan(stmt, model, filters)
        .order_by(model.id.desc())
        .limit(MODERATION_LISTE_BRANCH_LIMIT)
    )


def fetch_moderation_list_rows(filters: dict) -> list[ModerasyonListeSatir]:
    """Filtrelenmiş moderasyon satırları (tur başına en fazla 500, analiz JOIN ile)."""
    tur_filtre = filters.get("tur")
    branches = []
    if tur_filtre in (None, "", "kaynak"):
        branches.append(_branch_stmt(Kaynak, "kaynak", filters))
    if tur_filtre in (None, "", "atik"):
        branches.append(_branch_stmt(Atik, "atik", filters))
    if not branches:
        return []

    rows: list[ModerasyonListeSatir] = []
    for branch in branches:
        for row in db.session.execute(branch).mappings().all():
            rows.append(
                ModerasyonListeSatir(
                    tur=row["tur"],
                    ilan_id=row["ilan_id"],
                    moderation_status=row["moderation_status"],
                    ai_risk_score=row["ai_risk_score"],
                    tarih=row["tarih"],
                    baslik=row["baslik"],
                    aciklama=row["aciklama"],
                    user_id=row["user_id"],
                    kategori=row["kategori"],
                    alt_kategori=row["alt_kategori"],
                    resim=row["resim"],
                    final_risk=row["final_risk"],
                    spam_score=row["spam_score"],
                    duplicate_score=row["duplicate_score"],
                    category=row["category"],
                    purpose=row["purpose"],
                    confidence=row["confidence"],
                )
            )
    return rows


def _ilan_load_options(model):
    columns = [
        model.id,
        model.baslik,
        model.aciklama,
        model.user_id,
        model.tarih,
        model.moderation_status,
        model.ai_risk_score,
        model.kategori,
        model.resim,
    ]
    if model is Kaynak:
        columns.append(model.durum)
    return [
        load_only(*columns),
        joinedload(model.sahip).load_only(User.id, User.username),
        selectinload(model.fotograflar),
    ]


def batch_load_ilans(rows: list[ModerasyonListeSatir]) -> dict[tuple[str, int], Any]:
    """Liste satırları için ilan ORM nesnelerini toplu yükler."""
    kaynak_ids = [r.ilan_id for r in rows if r.tur == "kaynak"]
    atik_ids = [r.ilan_id for r in rows if r.tur == "atik"]
    loaded: dict[tuple[str, int], Any] = {}
    if kaynak_ids:
        for ilan in (
            Kaynak.query.options(*_ilan_load_options(Kaynak))
            .filter(Kaynak.id.in_(kaynak_ids))
            .all()
        ):
            loaded[("kaynak", ilan.id)] = ilan
    if atik_ids:
        for ilan in (
            Atik.query.options(*_ilan_load_options(Atik))
            .filter(Atik.id.in_(atik_ids))
            .all()
        ):
            loaded[("atik", ilan.id)] = ilan
    return loaded


def sorted_moderation_rows(filters: dict) -> list[ModerasyonListeSatir]:
    """Öncelik sırasına göre sıralanmış satırlar (mevcut Python sort korunur)."""
    rows = fetch_moderation_list_rows(filters)
    return sort_moderation_items(rows)
