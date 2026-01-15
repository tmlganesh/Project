import sqlite3

DB_NAME = "bus_data.db"   # ⚠️ must match app.py

conn = sqlite3.connect(DB_NAME)
cur = conn.cursor()

print("\n📌 TABLES IN DATABASE:")
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print(cur.fetchall())

print("\n📌 BUS MASTER DATA:")
try:
    cur.execute("SELECT * FROM buses")
    rows = cur.fetchall()
    if not rows:
        print("❌ No data found in buses table")
    else:
        for r in rows:
            print(r)
except Exception as e:
    print("❌ Error:", e)

conn.close()
