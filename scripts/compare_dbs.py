import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHS = [ROOT / "site.db", ROOT / "instance" / "site.db"]
TABLES = ["user", "kaynak", "atik", "mesaj", "comment", "bildirim", "favori"]

for p in PATHS:
    print(f"=== {p} ===")
    if not p.exists():
        print("  (dosya yok)")
        continue
    print(f"  Boyut: {p.stat().st_size} byte")
    print(f"  Son degisiklik: {p.stat().st_mtime}")
    conn = sqlite3.connect(p)
    for t in TABLES:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)
        ).fetchone()
        if row:
            n = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
            print(f"  {t}: {n}")
    conn.close()
    print()
