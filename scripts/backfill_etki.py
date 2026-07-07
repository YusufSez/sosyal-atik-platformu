"""Mevcut teslim edilmiş ilanlar için çevresel etki backfill."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from factory import create_app
from services.impact import backfill_mevcut_teslimler


def main():
    app = create_app()
    with app.app_context():
        count = backfill_mevcut_teslimler()
        print(f"Backfill tamamlandı: {count} yeni etki kaydı oluşturuldu.")


if __name__ == "__main__":
    main()
