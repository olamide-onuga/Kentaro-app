import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'kentaro.db')

def run_migrations():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Checking users table...")
    cursor.execute("PRAGMA table_info(users)")
    cols = [col[1] for col in cursor.fetchall()]
    if 'display_name' not in cols:
        print("Adding display_name to users...")
        cursor.execute("ALTER TABLE users ADD COLUMN display_name VARCHAR(64)")

    print("Checking support_tickets table...")
    cursor.execute("PRAGMA table_info(support_tickets)")
    ticket_cols = [col[1] for col in cursor.fetchall()]
    
    new_ticket_cols = [
        ('category', 'VARCHAR(64) DEFAULT "general"'),
        ('description', 'TEXT'),
        ('attachment_url', 'VARCHAR(255)'),
        ('accepted_at', 'DATETIME'),
        ('rating', 'INTEGER'),
        ('rating_feedback', 'TEXT'),
        ('rated_at', 'DATETIME')
    ]
    for col_name, col_def in new_ticket_cols:
        if col_name not in ticket_cols:
            print(f"Adding {col_name} to support_tickets...")
            cursor.execute(f"ALTER TABLE support_tickets ADD COLUMN {col_name} {col_def}")

    print("Checking ticket_messages table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
            sender_id INTEGER NOT NULL REFERENCES users(id),
            message TEXT NOT NULL,
            is_system BOOLEAN DEFAULT 0,
            attachment_url VARCHAR(255),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_ticket_messages_ticket_id ON ticket_messages(ticket_id)")

    print("Checking support_ratings table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS support_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL UNIQUE REFERENCES support_tickets(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            admin_id INTEGER NOT NULL REFERENCES users(id),
            rating INTEGER NOT NULL,
            feedback TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("Checking custom_program_offers table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_program_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_ref VARCHAR(32) UNIQUE,
            coach_id INTEGER NOT NULL REFERENCES coach_profiles(id),
            client_id INTEGER NOT NULL REFERENCES client_profiles(id),
            program_id INTEGER REFERENCES programs(id),
            post_id INTEGER REFERENCES client_posts(id),
            title VARCHAR(128) NOT NULL,
            description TEXT,
            amount FLOAT NOT NULL,
            currency VARCHAR(8) DEFAULT 'USD',
            duration_weeks INTEGER DEFAULT 4,
            frequency VARCHAR(64),
            goals TEXT,
            instructions TEXT,
            terms TEXT,
            start_date DATE,
            status VARCHAR(32) DEFAULT 'sent',
            payment_reference VARCHAR(128),
            paid_at DATETIME,
            declined_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_custom_program_offers_coach ON custom_program_offers(coach_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_custom_program_offers_client ON custom_program_offers(client_id)")

    print("Checking chat_messages table for offer_id...")
    cursor.execute("PRAGMA table_info(chat_messages)")
    chat_cols = [col[1] for col in cursor.fetchall()]
    if 'offer_id' not in chat_cols:
        print("Adding offer_id to chat_messages...")
        cursor.execute("ALTER TABLE chat_messages ADD COLUMN offer_id INTEGER REFERENCES custom_program_offers(id)")

    conn.commit()
    conn.close()
    print("Database migrations applied successfully without data loss!")

if __name__ == '__main__':
    run_migrations()
