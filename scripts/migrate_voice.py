import sqlite3
import os
import glob

def run():
    db_paths = glob.glob('*.db') + glob.glob('instance/*.db')
    print('Found DB paths:', db_paths)
    for p in set(db_paths):
        if not os.path.exists(p):
            continue
        conn = sqlite3.connect(p)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages';")
        if cur.fetchone():
            cur.execute("PRAGMA table_info(chat_messages);")
            cols = [r[1] for r in cur.fetchall()]
            print(f"{p} chat_messages columns: {cols}")
            if 'voice_url' not in cols:
                print(f"Adding voice_url to {p}...")
                cur.execute("ALTER TABLE chat_messages ADD COLUMN voice_url VARCHAR(255);")
                conn.commit()
                print("Added!")
            else:
                print(f"voice_url already in {p}")
        conn.close()

if __name__ == '__main__':
    run()
