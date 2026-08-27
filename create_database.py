import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'carwars.db')

def create_database():
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ── Games table ───────────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            map         TEXT NOT NULL,
            max_players INTEGER NOT NULL,
            division    INTEGER NOT NULL,
            created_by  TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'waiting',
            initial_speed TEXT NOT NULL,
            auto_start  INTEGER NOT NULL DEFAULT 0
        )
    ''')

    # ── Game players table ────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_players (
            game_id         TEXT    NOT NULL,
            username        TEXT    NOT NULL,
            design          TEXT,
            joined_at       TEXT    NOT NULL,
            position_number INTEGER NOT NULL DEFAULT 0,
            is_ready        INTEGER NOT NULL DEFAULT 0,
            car_image       TEXT,
            PRIMARY KEY (game_id, username),
            FOREIGN KEY (game_id) REFERENCES games(id)
        )
    ''')

    # ── Designs table ─────────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS designs (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            filename    TEXT NOT NULL,
            owner       TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            is_private  INTEGER NOT NULL DEFAULT 0
        )
    ''')

    # ── Maps table ────────────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS maps (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            filename    TEXT NOT NULL,
            uploaded_by TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        )
    ''')

    # ── Spectators table ──────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS spectators (
            game_id    TEXT NOT NULL,
            username   TEXT NOT NULL,
            joined_at  TEXT NOT NULL,
            PRIMARY KEY (game_id, username),
            FOREIGN KEY (game_id) REFERENCES games(id)
        )
    ''')

    # ── Car Images table ──────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS car_images (
            name        TEXT PRIMARY KEY,
            owner       TEXT NOT NULL,
            base64_data TEXT NOT NULL,
            is_private  INTEGER NOT NULL DEFAULT 0,
            uploaded_at TEXT NOT NULL
        )
    ''')

    # ── Starting Position Images table ────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS starting_position_images (
            name        TEXT PRIMARY KEY,
            base64_data TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        )
    ''')

    conn.commit()
    conn.close()

    print(f'Database created successfully at: {DB_PATH}')
    print('Tables created:')
    print('  - games')
    print('  - game_players')
    print('  - designs')
    print('  - maps')
    print('  - spectators')
    print('  - car_images')

def purge_database():
    if not os.path.exists(DB_PATH):
        print('No database found — nothing to purge.')
        return

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DELETE FROM spectators')
    cursor.execute('DELETE FROM game_players')
    cursor.execute('DELETE FROM games')
    cursor.execute('DELETE FROM designs')
    cursor.execute('DELETE FROM maps')
    cursor.execute('DELETE FROM car_images')
    cursor.execute('DELETE FROM starting_position_images')

    conn.commit()
    conn.close()

    print('Purge complete. All table contents have been deleted.')
    print('Tables purged:')
    print('  - spectators')
    print('  - game_players')
    print('  - games')
    print('  - designs')
    print('  - maps')
    print('  - car_images')
    print('  - starting_position_images')

if __name__ == '__main__':
    print('Car Wars Online — Database Utility')
    print('------------------------------------')
    print('1. Create database (safe — skips existing tables)')
    print('2. Purge all data (WARNING: deletes all records)')
    print()

    choice = input('Enter choice (1 or 2): ').strip()

    if choice == '1':
        create_database()
    elif choice == '2':
        confirm = input('Are you sure you want to delete ALL data? Type YES to confirm: ').strip()
        if confirm == 'YES':
            purge_database()
        else:
            print('Purge cancelled.')
    else:
        print('Invalid choice. Please enter 1 or 2.')