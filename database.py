import sqlite3
import uuid
import os
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'carwars.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ── Games ─────────────────────────────────────────────────────────────────────
def create_game(name, map_file, max_players, division, created_by, initial_speed,
                auto_start=False):
    conn = get_db()
    try:
        # Check for an exact, case-sensitive match on the game name
        existing = conn.execute(
            'SELECT 1 FROM games WHERE name = ?', (name,)
        ).fetchone()
        
        # If an exact match is found, reject it immediately
        if existing:
            raise ValueError(f"A game named '{name}' already exists.")

        # Otherwise, proceed with creating the unique game entry
        game_id = str(uuid.uuid4())
        conn.execute('''
                        INSERT INTO games (id, name, map, max_players, division,
                        created_by, created_at, status, initial_speed, auto_start)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
            game_id, 
            name, 
            map_file, 
            max_players, 
            division, 
            created_by, 
            datetime.now().isoformat(),  # 1st Shifted Fix: Aligned to created_at
            'waiting',                   # 2nd Shifted Fix: Aligned to status
            initial_speed,               # 3rd Shifted Fix: Aligned to initial_speed
            1 if auto_start else 0
        ))
        conn.commit()
        return game_id
    finally:
        conn.close()        

def get_all_games():
    conn = get_db()
    try:
        rows = conn.execute(
            'SELECT * FROM games ORDER BY created_at DESC'
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_game(game_id):
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT * FROM games WHERE id = ?', (game_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def update_game_status(game_id, status):
    conn = get_db()
    try:
        conn.execute(
            'UPDATE games SET status = ? WHERE id = ?', (status, game_id)
        )
        conn.commit()
    finally:
        conn.close()

def delete_game(game_id):
    conn = get_db()
    try:
        conn.execute('DELETE FROM game_players WHERE game_id = ?', (game_id,))
        conn.execute('DELETE FROM spectators   WHERE game_id = ?', (game_id,))
        conn.execute('DELETE FROM games        WHERE id = ?',      (game_id,))
        conn.commit()
    finally:
        conn.close()

def get_startable_games_for_user(username):
    """
    Returns games that:
      - were created by this user
      - have status 'waiting'
      - have exactly max_players players joined (game is full)
    """
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT g.*,
                   COUNT(gp.username) AS joined_count
            FROM games g
            LEFT JOIN game_players gp ON gp.game_id = g.id
            WHERE g.created_by = ?
              AND g.status     = 'waiting'
            GROUP BY g.id
            ORDER BY g.created_at DESC
        ''', (username,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

# ── Game Players ──────────────────────────────────────────────────────────────

def join_game(game_id, username, position_number=0):
    conn = get_db()
    try:
        conn.execute('''
            INSERT INTO game_players
                (game_id, username, design, joined_at, position_number,
                 is_ready, car_image)
            VALUES (?, ?, NULL, ?, ?, 0, NULL)
        ''', (game_id, username, datetime.now().isoformat(), position_number))
        conn.commit()
    finally:
        conn.close()

def get_game_players(game_id):
    conn = get_db()
    try:
        rows = conn.execute(
            'SELECT * FROM game_players WHERE game_id = ? ORDER BY joined_at',
            (game_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def set_player_design(game_id, username, design_filename):
    conn = get_db()
    try:
        conn.execute('''
            UPDATE game_players SET design = ?
            WHERE game_id = ? AND username = ?
        ''', (design_filename, game_id, username))
        conn.commit()
    finally:
        conn.close()

def set_player_car_image(game_id, username, car_image_name):
    """Assign a car image name to a player in a game."""
    conn = get_db()
    try:
        conn.execute('''
            UPDATE game_players SET car_image = ?
            WHERE game_id = ? AND username = ?
        ''', (car_image_name, game_id, username))
        conn.commit()
    finally:
        conn.close()

def set_player_ready(game_id, username, is_ready: bool):
    conn = get_db()
    try:
        conn.execute('''
            UPDATE game_players SET is_ready = ?
            WHERE game_id = ? AND username = ?
        ''', (1 if is_ready else 0, game_id, username))
        conn.commit()
    finally:
        conn.close()

def set_player_position(game_id, username, position_number: int):
    conn = get_db()
    try:
        conn.execute('''
            UPDATE game_players SET position_number = ?
            WHERE game_id = ? AND username = ?
        ''', (position_number, game_id, username))
        conn.commit()
    finally:
        conn.close()

def get_player_ready_status(game_id) -> dict:
    conn = get_db()
    try:
        rows    = conn.execute('''
            SELECT username, position_number, is_ready
            FROM game_players
            WHERE game_id = ?
            ORDER BY position_number, joined_at
        ''', (game_id,)).fetchall()
        players   = [dict(r) for r in rows]
        all_ready = len(players) > 0 and all(p['is_ready'] for p in players)
        return {
            'players':   players,
            'all_ready': all_ready,
            'count':     len(players)
        }
    finally:
        conn.close()

def leave_game(game_id, username):
    conn = get_db()
    try:
        conn.execute(
            'DELETE FROM game_players WHERE game_id = ? AND username = ?',
            (game_id, username)
        )
        conn.commit()
    finally:
        conn.close()

def is_player_in_game(game_id, username) -> bool:
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT 1 FROM game_players WHERE game_id = ? AND username = ?',
            (game_id, username)
        ).fetchone()
        return row is not None
    finally:
        conn.close()

# ── Spectators ────────────────────────────────────────────────────────────────

def add_spectator(game_id, username):
    conn = get_db()
    try:
        conn.execute('''
            INSERT OR IGNORE INTO spectators (game_id, username, joined_at)
            VALUES (?, ?, ?)
        ''', (game_id, username, datetime.now().isoformat()))
        conn.commit()
    finally:
        conn.close()

def get_spectators(game_id):
    conn = get_db()
    try:
        rows = conn.execute(
            'SELECT * FROM spectators WHERE game_id = ? ORDER BY joined_at',
            (game_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_spectator_count(game_id) -> int:
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT COUNT(*) as count FROM spectators WHERE game_id = ?',
            (game_id,)
        ).fetchone()
        return row['count']
    finally:
        conn.close()

def is_spectating(game_id, username) -> bool:
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT 1 FROM spectators WHERE game_id = ? AND username = ?',
            (game_id, username)
        ).fetchone()
        return row is not None
    finally:
        conn.close()

# ── Maps ──────────────────────────────────────────────────────────────────────

def register_map(filename, uploaded_by):
    conn = get_db()
    try:
        conn.execute('''
            INSERT OR IGNORE INTO maps
                (id, name, filename, uploaded_by, uploaded_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (str(uuid.uuid4()), filename, filename, uploaded_by,
              datetime.now().isoformat()))
        conn.commit()
    finally:
        conn.close()

def get_all_maps():
    conn = get_db()
    try:
        rows = conn.execute(
            'SELECT * FROM maps ORDER BY name'
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def delete_map_by_filename(filename):
    conn = get_db()
    try:
        conn.execute('DELETE FROM maps WHERE filename = ?', (filename,))
        conn.commit()
    finally:
        conn.close()

# ── Designs ───────────────────────────────────────────────────────────────────

def register_design(filename, uploaded_by, is_private=False):
    conn = get_db()
    try:
        conn.execute('''
            INSERT OR IGNORE INTO designs
                (id, name, filename, owner, uploaded_at, is_private)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (str(uuid.uuid4()), filename, filename, uploaded_by,
              datetime.now().isoformat(), 1 if is_private else 0))
        conn.commit()
    finally:
        conn.close()

def get_all_designs():
    conn = get_db()
    try:
        rows = conn.execute(
            'SELECT * FROM designs WHERE is_private = 0 ORDER BY name'
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_designs_by_owner(username):
    conn = get_db()
    try:
        rows = conn.execute(
            'SELECT * FROM designs WHERE owner = ? ORDER BY name',
            (username,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def delete_design_by_filename(filename):
    conn = get_db()
    try:
        conn.execute('DELETE FROM designs WHERE filename = ?', (filename,))
        conn.commit()
    finally:
        conn.close()

# ── Car Images ────────────────────────────────────────────────────────────────

def register_car_image(name, owner, base64_data, is_private=False):
    """
    Store a car image as a base64 string in the database.
    name is the primary key — must be unique across all users.
    Returns True on success, False if name already exists.
    """
    conn = get_db()
    try:
        existing = conn.execute(
            'SELECT 1 FROM car_images WHERE name = ?', (name,)
        ).fetchone()
        if existing:
            return False
        conn.execute('''
            INSERT INTO car_images (name, owner, base64_data, is_private, uploaded_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, owner, base64_data, 1 if is_private else 0,
              datetime.now().isoformat()))
        conn.commit()
        return True
    finally:
        conn.close()

def get_all_car_images():
    """Return all public car images."""
    conn = get_db()
    try:
        rows = conn.execute(
            'SELECT name, owner, is_private, uploaded_at FROM car_images '
            'WHERE is_private = 0 ORDER BY name'
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_car_images_for_user(username):
    """
    Return all car images visible to this user:
    all public images plus this user's own private images.
    """
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT name, owner, is_private, uploaded_at
            FROM car_images
            WHERE is_private = 0
               OR owner = ?
            ORDER BY name
        ''', (username,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_car_image_by_name(name):
    """Return the full car image record including base64_data."""
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT * FROM car_images WHERE name = ?', (name,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def delete_car_image(name):
    conn = get_db()
    try:
        conn.execute('DELETE FROM car_images WHERE name = ?', (name,))
        conn.commit()
    finally:
        conn.close()

def update_car_image_privacy(name, is_private: bool):
    conn = get_db()
    try:
        conn.execute(
            'UPDATE car_images SET is_private = ? WHERE name = ?',
            (1 if is_private else 0, name)
        )
        conn.commit()
    finally:
        conn.close()

# ── Starting Position Images ───────────────────────────────────────────────────

def register_starting_position_image(name: str, base64_data: str) -> bool:
    """
    Store a starting position image as a base64 string.
    name is the primary key — e.g. 'blue', 'red', etc.
    Returns True on success, False if name already exists.
    Use replace=True to overwrite an existing entry.
    """
    conn = get_db()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO starting_position_images
                (name, base64_data, uploaded_at)
            VALUES (?, ?, ?)
        ''', (name, base64_data, datetime.now().isoformat()))
        conn.commit()
        return True
    except Exception as e:
        print(f'Error registering starting position image "{name}": {e}')
        return False
    finally:
        conn.close()

def get_starting_position_image(name: str):
    """Return the full starting position image record by name."""
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT * FROM starting_position_images WHERE name = ?',
            (name,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_all_starting_position_images():
    """Return all starting position image records (without base64 data)."""
    conn = get_db()
    try:
        rows = conn.execute(
            'SELECT name, uploaded_at FROM starting_position_images ORDER BY name'
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def delete_starting_position_image(name: str):
    conn = get_db()
    try:
        conn.execute(
            'DELETE FROM starting_position_images WHERE name = ?', (name,)
        )
        conn.commit()
    finally:
        conn.close()
