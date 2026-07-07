"""Kullanıcıya kurum/belediye analiz paneli yetkisi verir."""
import sqlite3
import sys

email = (sys.argv[1] if len(sys.argv) > 1 else "admin@gmail.com").strip().lower()

conn = sqlite3.connect("site.db")
cur = conn.cursor()
cur.execute("SELECT id, email, username, is_kurum FROM user WHERE lower(email) = ?", (email,))
row = cur.fetchone()
if not row:
    print(f"Kullanıcı bulunamadı: {email}")
    conn.close()
    sys.exit(1)

print(f"Önce: id={row[0]}, email={row[1]}, is_kurum={row[3]}")
cur.execute("UPDATE user SET is_kurum = 1 WHERE id = ?", (row[0],))
conn.commit()
cur.execute("SELECT is_kurum FROM user WHERE id = ?", (row[0],))
print(f"Sonra: is_kurum={cur.fetchone()[0]}")
conn.close()
print("Tamam. /kurum/analiz adresine gidebilirsiniz.")
