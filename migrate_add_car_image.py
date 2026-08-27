import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'carwars.db')

def migrate():
    if not os.path.exists(DB_PATH):
        print('Database not found. Run create_database.py first.')
        return

    conn = sqlite3.connect(DB_PATH)

    conn.execute('''
        CREATE TABLE IF NOT EXISTS car_images (
            name        TEXT PRIMARY KEY,
            owner       TEXT NOT NULL,
            base64_data TEXT NOT NULL,
            is_private  INTEGER NOT NULL DEFAULT 0,
            uploaded_at TEXT NOT NULL
        )
    ''')

    conn.commit()
    conn.close()
    print('Migration complete. Table "car_images" created.')

if __name__ == '__main__':
    migrate()