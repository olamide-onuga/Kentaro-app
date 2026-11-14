import sqlite3

db_path = r'C:\Users\Kentaro\.gemini\antigravity\scratch\kentaro\kentaro.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# 1. Update client_posts table with rich marketplace request fields
columns_to_add = [
    ("specialization", "VARCHAR(64) DEFAULT 'Calisthenics & Strength'"),
    ("skill_level", "VARCHAR(32) DEFAULT 'Beginner'"),
    ("experience", "VARCHAR(64) DEFAULT '0-6 Months'"),
    ("min_budget", "REAL DEFAULT NULL"),
    ("max_budget", "REAL DEFAULT NULL"),
    ("currency", "VARCHAR(8) DEFAULT 'USD'"),
    ("is_flexible_budget", "INTEGER DEFAULT 0"),
    ("expectations", "TEXT DEFAULT NULL"),
    ("preferred_duration", "VARCHAR(64) DEFAULT '12 Weeks'"),
    ("comm_preference", "VARCHAR(64) DEFAULT 'In-App Chat & Voice Notes'"),
    ("fulfilled_at", "DATETIME DEFAULT NULL"),
    ("fulfilled_coach_id", "INTEGER DEFAULT NULL"),
    ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
]

for col_name, col_type in columns_to_add:
    try:
        c.execute(f"ALTER TABLE client_posts ADD COLUMN {col_name} {col_type}")
        print(f"Added column {col_name} to client_posts")
    except Exception as e:
        print(f"Column {col_name} already exists or error: {e}")

# 2. Add offer_id to client_contracts if not exists
try:
    c.execute("ALTER TABLE client_contracts ADD COLUMN offer_id INTEGER REFERENCES custom_program_offers(id)")
    print("Added offer_id to client_contracts")
except Exception as e:
    print(f"offer_id already exists in client_contracts: {e}")

conn.commit()

# Verify client_posts columns
c.execute("PRAGMA table_info(client_posts)")
print("Updated client_posts columns:", [r[1] for r in c.fetchall()])

conn.close()
print("Migration completed successfully!")
