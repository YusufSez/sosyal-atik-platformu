"""Kullanıcıya admin yetkisi verir. Kullanım: python scripts/set_admin.py admin@gmail.com"""
import sqlite3
import sys

email = (sys.argv[1] if len(sys.argv) > 1 else "admin@gmail.com").strip().lower()
db_path = "site.db"

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT id, email, username, is_admin FROM user WHERE lower(email) = ?", (email,))
row = cur.fetchone()
if not row:
    print(f"Kullanıcı bulunamadı: {email}")
    conn.close()
    sys.exit(1)

print(f"Önce: id={row[0]}, email={row[1]}, username={row[2]}, is_admin={row[3]}")
cur.execute("UPDATE user SET is_admin = 1 WHERE id = ?", (row[0],))
conn.commit()
cur.execute("SELECT id, email, username, is_admin FROM user WHERE id = ?", (row[0],))
updated = cur.fetchone()
print(f"Sonra: id={updated[0]}, email={updated[1]}, username={updated[2]}, is_admin={updated[3]}")
conn.close()
print("Tamam. Çıkış yapıp tekrar giriş yapın, ardından /admin adresine gidin.")
