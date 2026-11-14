import os, sqlite3

DB_PATH = os.path.join(r'C:/Users/Kentaro/.gemini/antigravity/scratch/kentaro', 'kentaro.db')

if not os.path.exists(DB_PATH):
    raise FileNotFoundError(f'Database not found at {DB_PATH}')

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Check if the column already exists
cur.execute("PRAGMA table_info(users)")
columns = [row[1] for row in cur.fetchall()]
if 'online' in columns:
    print('Column "online" already exists in users table.')
else:
    cur.execute('ALTER TABLE users ADD COLUMN online INTEGER NOT NULL DEFAULT 0')
    conn.commit()
    print('Added column "online" to users table.')

conn.close()
