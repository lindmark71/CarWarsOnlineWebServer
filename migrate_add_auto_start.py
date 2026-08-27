import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'carwars.db')

def migrate():
    if not os.path.exists(DB_PATH):
        print('Database not found. Run create_database.py first.')
        return

    conn     = sqlite3.connect(DB_PATH)
    existing = [row[1] for row in
                conn.execute('PRAGMA table_info(games)').fetchall()]

    if 'auto_start' not in existing:
        conn.execute('''
            ALTER TABLE games
            ADD COLUMN auto_start INTEGER NOT NULL DEFAULT 0
        ''')
        conn.commit()
        print('Migration complete. Column "auto_start" added to games table.')
    else:
        print('Nothing to migrate — "auto_start" column already exists.')

    conn.close()

if __name__ == '__main__':
    migrate()