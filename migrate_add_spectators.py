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
        CREATE TABLE IF NOT EXISTS spectators (
            game_id    TEXT NOT NULL,
            username   TEXT NOT NULL,
            joined_at  TEXT NOT NULL,
            PRIMARY KEY (game_id, username),
            FOREIGN KEY (game_id) REFERENCES games(id)
        )
    ''')
    conn.commit()
    conn.close()
    print('Migration complete. Table "spectators" created.')

if __name__ == '__main__':
    migrate()
