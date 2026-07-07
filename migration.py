"""Veritabanı migration scripti."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factory import create_app
from extensions import db
from models import AtikMerkezi
from services.impact import backfill_mevcut_teslimler, sync_etki_ilan_durumu
from services.ilan_images import backfill_ilan_resimleri
from utils import ensure_schema


def run_migration():
    app = create_app()
    with app.app_context():
        print("Migration başlıyor...")
        db.create_all()
        ensure_schema()

        if AtikMerkezi.query.count() == 0:
            print("Örnek atık merkezleri ekleniyor...")
            db.session.add_all([
                AtikMerkezi(ad="Kadıköy Atık Merkezi", latitude=40.99, longitude=29.03, adres="Kadıköy"),
                AtikMerkezi(ad="Beşiktaş Atık Merkezi", latitude=41.04, longitude=29.00, adres="Beşiktaş"),
                AtikMerkezi(ad="Üsküdar Atık Merkezi", latitude=41.02, longitude=29.02, adres="Üsküdar"),
            ])
            db.session.commit()

        backfill_count = backfill_mevcut_teslimler()
        if backfill_count:
            print(f"Çevresel etki backfill: {backfill_count} kayıt oluşturuldu.")

        sync_count = sync_etki_ilan_durumu()
        if sync_count:
            print(f"Çevresel etki senkron: {sync_count} tutarsız kayıt silindi.")

        resim_count = backfill_ilan_resimleri()
        if resim_count:
            print(f"İlan fotoğraf backfill: {resim_count} kayıt oluşturuldu.")

        print("Migration tamamlandı.")


if __name__ == "__main__":
    run_migration()
