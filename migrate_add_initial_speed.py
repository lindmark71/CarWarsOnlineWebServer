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

    if 'initial_speed' not in existing:
        conn.execute('''
            ALTER TABLE games
            ADD COLUMN initial_speed TEXT NOT NULL DEFAULT 0
        ''')
        conn.commit()
        print('Migration complete. Column "initial_speed" added to games table.')
    else:
        print('Nothing to migrate — "initial_speed" column already exists.')

    conn.close()

if __name__ == '__main__':
    migrate()