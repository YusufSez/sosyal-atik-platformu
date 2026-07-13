"""Kurumsal marketplace rol atama.

Kullanım:
  python scripts/set_marketplace_role.py firma@ornek.com company
  python scripts/set_marketplace_role.py kurum@ornek.com institution
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "instance" / "site.db"
if not DB.exists():
    DB = ROOT / "site.db"

ALLOWED = {"company", "institution"}


def main():
    email = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    role = (sys.argv[2] if len(sys.argv) > 2 else "").strip().lower()
    if not email or role not in ALLOWED:
        print("Kullanım: python scripts/set_marketplace_role.py <email> <company|institution>")
        sys.exit(1)
    if not DB.exists():
        print(f"Veritabanı bulunamadı: {DB}")
        sys.exit(1)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "UPDATE user SET role = ?, is_kurum = 1 WHERE lower(email) = ?",
        (role, email),
    )
    conn.commit()
    print(f"Güncellenen satır: {cur.rowcount} ({email} → role={role}, is_kurum=1)")
    conn.close()


if __name__ == "__main__":
    main()
