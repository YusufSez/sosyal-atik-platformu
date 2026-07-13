"""Bakanlık (ministry) rolü atama scripti.

Kullanım:
  python scripts/set_ministry.py bakanlik@example.com
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "instance" / "site.db"
if not DB.exists():
    DB = ROOT / "site.db"


def main():
    email = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if not email:
        print("Kullanım: python scripts/set_ministry.py <email>")
        sys.exit(1)
    if not DB.exists():
        print(f"Veritabanı bulunamadı: {DB}")
        sys.exit(1)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "UPDATE user SET role = 'ministry', is_admin = 0 WHERE lower(email) = ?",
        (email,),
    )
    conn.commit()
    print(f"Güncellenen satır: {cur.rowcount} ({email} → role=ministry)")
    conn.close()


if __name__ == "__main__":
    main()
