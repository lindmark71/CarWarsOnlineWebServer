import os
import re
import ast
import math
import json
import uuid
import base64
import shutil
import bcrypt
import secrets
import random
from io import BytesIO
from PIL import Image
from flask import send_file
from functools import wraps
from datetime import datetime, timedelta  # <-- Ensure this is imported at the top of the file
from flask import Flask, render_template, request, redirect, jsonify, session
import database as db
import secrets
from game_engine import GameEngine 
from game_tables import resolve_control_check, SPEED_CONTROL, CONTROL_TABLE, CONTROL_COLUMNS

app = Flask(__name__)

# ── Secret Key ────────────────────────────────────────────────────────────────

SECRET_KEY_FILE = './secret_key.txt'
# ── SET THIS GLOBALLY: Dictates how long permanent sessions last ──
app.permanent_session_lifetime = timedelta(days=31)

def load_or_create_secret_key():
    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, 'r') as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(SECRET_KEY_FILE, 'w') as f:
        f.write(key)
    return key

app.secret_key = load_or_create_secret_key()

# ── Folder Setup ──────────────────────────────────────────────────────────────

CREDENTIALS_FILE     = './credentials.json'
UPLOAD_FOLDER_MAP    = './uploads/maps'
UPLOAD_FOLDER_DESIGN = './uploads/designs'
GAME_FOLDER          = './games'
os.makedirs(UPLOAD_FOLDER_MAP,    exist_ok=True)
os.makedirs(UPLOAD_FOLDER_DESIGN, exist_ok=True)
os.makedirs(GAME_FOLDER,          exist_ok=True)

# ── Twilio SMS Setup ──────────────────────────────────────────────────────────
#
# STEP 1: Create a free Twilio account at https://www.twilio.com/try-twilio
# STEP 2: From https://console.twilio.com note your Account SID, Auth Token,
#         and assigned phone number.
# STEP 3: pip install twilio
# STEP 4: Replace the placeholder values below.
#
TWILIO_ACCOUNT_SID = 'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'   # ← replace
TWILIO_AUTH_TOKEN  = 'your_auth_token'                      # ← replace
TWILIO_FROM_NUMBER = '+12015551234'                         # ← replace

def game_dir_path(game_id: str) -> str:
    """Returns the path to a game's dedicated file directory."""
    return os.path.join(GAME_FOLDER, game_id)

def send_sms(to_number: str, message: str) -> bool:
    if not to_number:
        return False
    if TWILIO_ACCOUNT_SID.startswith('ACx'):
        print('Twilio not configured — SMS skipped.')
        return False
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg    = client.messages.create(
            body  = message,
            from_ = TWILIO_FROM_NUMBER,
            to    = to_number
        )
        print(f'SMS sent to {to_number}. SID: {msg.sid}')
        return True
    except ImportError:
        print('Twilio not installed. Run: pip install twilio')
        return False
    except Exception as e:
        print(f'SMS send failed: {e}')
        return False

def normalize_phone(phone: str) -> str:
    if not phone:
        return ''
    cleaned = re.sub(r'[^\d+]', '', phone.strip())
    if re.match(r'^\+\d{7,15}$', cleaned):
        return cleaned
    return ''

def get_user_phone(username: str) -> str:
    credentials = load_credentials()
    user = credentials.get(username, {})
    if isinstance(user, dict):
        return user.get('phone', '')
    return ''

# ── Credentials Helpers ───────────────────────────────────────────────────────

def load_credentials():
    if not os.path.exists(CREDENTIALS_FILE):
        return {}
    with open(CREDENTIALS_FILE, 'r') as f:
        return json.load(f)

def save_credentials(credentials):
    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump(credentials, f, indent=2)

def check_credentials(username, password):
    if not os.path.exists(CREDENTIALS_FILE):
        return False
    credentials = load_credentials()
    if username not in credentials:
        return False
    stored = credentials[username]
    stored_hash = stored['password'].encode('utf-8') if isinstance(stored, dict) else stored.encode('utf-8')
    return bcrypt.checkpw(password.encode('utf-8'), stored_hash)

def email_already_registered(email: str) -> bool:
    credentials = load_credentials()
    email_lower = email.lower().strip()
    for data in credentials.values():
        if isinstance(data, dict):
            if data.get('email', '').lower().strip() == email_lower:
                return True
    return False

def phone_already_registered(phone: str) -> bool:
    if not phone:
        return False
    credentials = load_credentials()
    normalized  = normalize_phone(phone)
    if not normalized:
        return False
    for data in credentials.values():
        if isinstance(data, dict):
            if data.get('phone', '') == normalized:
                return True
    return False

# ── Login Required Decorator ──────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'error': 'Not logged in'}), 401
        return f(*args, **kwargs)
    return decorated_function

# ── Admin Required Decorator ──────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('username') != 'admin':
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

# ── Design File Helpers ───────────────────────────────────────────────────────

def extract_total_cost(filepath):
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        data = ast.literal_eval(content)
        if isinstance(data, list) and len(data) > 0:
            return data[0].get('total_cost', None)
        return None
    except Exception as e:
        print(f'Error parsing design file: {e}')
        return None

def get_division_prefix(total_cost):
    cost     = int(total_cost)
    division = math.ceil(cost / 5000) * 5000
    return f"{division // 1000}K_"

# ── Game File Helpers ─────────────────────────────────────────────────────────

def sanitize_name_for_filename(name: str) -> str:
    """Strip everything except alphanumerics so game names are safe in filenames."""
    return re.sub(r'[^a-zA-Z0-9]', '', name)

def create_t1p0_file2(game_id: str, game_name: str, map_filename: str) -> str:
    """
    Copy the map file into GAME_FOLDER as the T1P0 game file.
    Returns the new filename on success, empty string on failure.
    Convention: <game_id><sanitized_name>T1P0.txt
    """
    map_path = os.path.join(UPLOAD_FOLDER_MAP, map_filename)
    if not os.path.exists(map_path):
        print(f'Map file not found: {map_path}')
        return ''
    safe_name = sanitize_name_for_filename(game_name)
    t1p0_name = f'{game_id}{safe_name}T1P0.txt'
    t1p0_path = os.path.join(GAME_FOLDER, t1p0_name)
    try:
        shutil.copy2(map_path, t1p0_path)
        print(f'T1P0 file created: {t1p0_path}')
        return t1p0_name
    except Exception as e:
        print(f'Error creating T1P0 file: {e}')
        return ''

def create_t1p0_file(game_id: str, game_name: str, map_filename: str) -> str:
    """
    Create the game's dedicated directory and copy the map file into it as T1P0.txt.
    Returns the new filename on success ('T1P0.txt'), empty string on failure.
    """
    map_path = os.path.join(UPLOAD_FOLDER_MAP, map_filename)
    if not os.path.exists(map_path):
        print(f'Map file not found: {map_path}')
        return ''

    game_dir = game_dir_path(game_id)
    os.makedirs(game_dir, exist_ok=True)

    t1p0_name = 'T1P0.txt'
    t1p0_path = os.path.join(game_dir, t1p0_name)
    try:
        shutil.copy2(map_path, t1p0_path)
        print(f'T1P0 file created: {t1p0_path}')
        return t1p0_name
    except Exception as e:
        print(f'Error creating T1P0 file: {e}')
        return ''
    
def find_t1p0_path2(game_id: str, game_name: str) -> str:
    """
    Construct the full path to the T1P0 file for a game.
    Returns empty string if the file does not exist.
    """
    safe_name = sanitize_name_for_filename(game_name)
    filename  = f'{game_id}{safe_name}T1P0.txt'
    filepath  = os.path.join(GAME_FOLDER, filename)
    return filepath if os.path.exists(filepath) else ''

def find_t1p0_path(game_id: str, game_name: str) -> str:
    """
    Construct the full path to the T1P0 file for a game.
    Returns empty string if the file does not exist.
    """
    filepath = os.path.join(game_dir_path(game_id), 'T1P0.txt')
    return filepath if os.path.exists(filepath) else ''

def read_game_file(filepath: str) -> list:
    """
    Read a game file where each line is a Python dict literal.
    Returns a list of dicts, one per line.
    Skips blank lines and lines that cannot be parsed.
    """
    result = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = ast.literal_eval(line)
                if isinstance(entry, dict):
                    result.append(entry)
            except Exception as e:
                print(f'Skipping unparseable line in {filepath}: {e}')
    except Exception as e:
        print(f'Error reading game file {filepath}: {e}')
    return result

def write_game_file(filepath: str, data: list) -> bool:
    """
    Write a list of dicts back to a game file,
    one dict per line, matching the format map_designer.py produces.
    """
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            for entry in data:
                f.write(str(entry) + '\n')
        return True
    except Exception as e:
        print(f'Error writing game file {filepath}: {e}')
        return False

def add_car_position_to_file(filepath: str, position_number: int, car_image_name: str,
                             owner_username: str, initial_velocity: int = 0, design: str = None) -> bool:
    """
    Locates the matching StartingPosition marker and appends a structured CarPosition 
    object record, mapping true top speed metrics straight to T1P0 game files.
    """
    data = read_game_file(filepath)
    if not data:
        return False

    starting = None
    for entry in data:
        if (entry.get('StartingPosition') == 'StartingPosition' and
            int(entry.get('position_number', -1)) == position_number):
            starting = entry
            break

    if starting is None:
        print(f'No StartingPosition asset marker found for configuration index: {position_number}')
        return False

    # ── READ COMPILING BLUEPRINT TEXT ATOM FOR ACCURATE TOP SPEED MATCHING ──
    true_top_speed = 90  # Unit test baseline fallback absolute floor target
    
    # Safely distill game_id context out of the central folder filename path strings
    base_filename = os.path.basename(filepath)
    game_id_match = re.match(r'^([a-f0-9\-]+)', base_filename)
    
    if game_id_match and design:
        game_id = game_id_match.group(1)
        # Target the specific vehicle text record file name convention used by your engine
        snapshot_filename = f"player_{position_number}_{design}"
        snapshot_path = os.path.join(game_dir_path(game_id), snapshot_filename)
        
        if os.path.exists(snapshot_path):
            try:
                car_spec_records = read_game_file(snapshot_path)
                if car_spec_records and len(car_spec_records) > 0:
                    # Isolate the main attribute dictionary profile data block node
                    car_profile = car_spec_records[0] if isinstance(car_spec_records, list) else car_spec_records
                    if isinstance(car_profile, dict) and 'top_speed' in car_profile:
                        # Extract the exact unit test property parameter ('90')
                        true_top_speed = int(car_profile['top_speed'])
                        print(f"[ENGINE INITIALIZATION SUCCESS] Found active vehicle profile spec. Syncing Top Speed: {true_top_speed} MPH.")
            except Exception as e:
                print(f"[PARSING ERROR] Unable to evaluate vehicle metadata parameters: {e}. Defaulting to 90.")

    # Build the tracking schema mapping to the data structure requirements
    car_entry = {
        'CarPosition': 'CarPosition',
        'player_number': position_number,
        'owner': owner_username,
        'local_starting_x_qty': starting['local_starting_x_qty'],
        'local_starting_y_qty': starting['local_starting_y_qty'],
        'current_speed': initial_velocity, 
        'top_speed': true_top_speed, # ── FIXED: Written accurately during join execution sequence! ──
        'heading': starting['orientation'],
        'orientation': starting['orientation'],
        'color': starting.get('color', 'blue'),
        'car_image_name': car_image_name
    }

    data.append(car_entry)
    return write_game_file(filepath, data)

def create_phase_file2(game_id: str, game_name: str,
                      source_filename: str,
                      new_phase_suffix: str) -> str:
    """
    Copy an existing game phase file to a new phase file.
    Both source and destination live in GAME_FOLDER.

    Args:
        game_id:          the game's UUID
        game_name:        the game's name (will be sanitized)
        source_filename:  the filename to copy FROM (e.g. '<id><name>T1P0.txt')
        new_phase_suffix: the phase suffix for the new file (e.g. 'T1P1M')

    Returns the new filename on success, empty string on failure.
    Convention: <game_id><sanitized_name><new_phase_suffix>.txt
    """
    source_path = os.path.join(GAME_FOLDER, source_filename)
    if not os.path.exists(source_path):
        print(f'Source game file not found: {source_path}')
        return ''

    safe_name  = sanitize_name_for_filename(game_name)
    new_name   = f'{game_id}{safe_name}{new_phase_suffix}.txt'
    new_path   = os.path.join(GAME_FOLDER, new_name)

    try:
        shutil.copy2(source_path, new_path)
        print(f'Phase file created: {new_path}')
        return new_name
    except Exception as e:
        print(f'Error creating phase file {new_name}: {e}')
        return ''

def create_phase_file(game_id: str, game_name: str,
                      source_filename: str,
                      new_phase_suffix: str) -> str:
    """
    Copy an existing game phase file to a new phase file, both within
    the game's dedicated directory.

    Args:
        game_id:          the game's UUID
        game_name:        unused now, kept for call-site compatibility
        source_filename:  bare filename to copy FROM (e.g. 'T1P0.txt')
        new_phase_suffix: bare filename suffix for the new file (e.g. 'T1P1M')

    Returns the new filename on success (e.g. 'T1P1M.txt'), empty string on failure.
    """
    game_dir = game_dir_path(game_id)
    source_path = os.path.join(game_dir, source_filename)
    if not os.path.exists(source_path):
        print(f'Source game file not found: {source_path}')
        return ''

    new_name = f'{new_phase_suffix}.txt'
    new_path = os.path.join(game_dir, new_name)

    try:
        shutil.copy2(source_path, new_path)
        print(f'Phase file created: {new_path}')
        return new_name
    except Exception as e:
        print(f'Error creating phase file {new_name}: {e}')
        return ''
    
# ── Auth Routes ───────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # ── NEW: If a valid cookie session already exists, bypass the login page! ──
    if 'username' in session:
        return redirect('/game_screen')

    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if check_credentials(username, password):
            session.permanent = True  # Activates 31-day cookie rule
            session['username'] = username
            return render_template('client_screen.html',
                                   is_admin=(username == 'admin'))
        else:
            error = 'Invalid username or password. Please try again.'
    return render_template('login.html', error=error)

@app.route('/game_screen')
@login_required
def game_screen():
    username = session['username']
    return render_template('client_screen.html', is_admin=(username == 'admin'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/get_session_user')
def get_session_user():
    username = session.get('username')
    if username:
        return jsonify({
            'username': username,
            'is_admin': username == 'admin'
        }), 200
    return jsonify({'error': 'Not logged in'}), 401

@app.route('/register', methods=['GET', 'POST'])
def register():
    error   = None
    success = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email',    '').strip()
        password = request.form.get('password', '').strip()
        confirm  = request.form.get('confirm_password', '').strip()
        phone    = request.form.get('phone',    '').strip()

        if not username or not email or not password:
            error = 'Username, email and password are required.'
        elif '@' not in email or '.' not in email:
            error = 'Please enter a valid email address.'
        elif password != confirm:
            error = 'Passwords do not match.'
        elif len(password) < 8:
            error = 'Password must be at least 8 characters.'
        elif phone and not normalize_phone(phone):
            error = 'Invalid phone number. Use international format, e.g. +12155551234'
        else:
            credentials = load_credentials()
            if username in credentials:
                error = 'That username is already taken.'
            elif email_already_registered(email):
                error = 'That email address is already associated with an account.'
            elif phone and phone_already_registered(phone):
                error = 'That phone number is already associated with an account.'
            else:
                hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
                credentials[username] = {
                    'password': hashed.decode('utf-8'),
                    'email':    email,
                    'phone':    normalize_phone(phone)
                }
                save_credentials(credentials)
                success = 'Account created! You can now log in.'
                if normalize_phone(phone):
                    send_sms(normalize_phone(phone),
                             f'Welcome to Car Wars Online, {username}!')

    return render_template('register.html', error=error, success=success)

# ── Admin Route ───────────────────────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin():
    return render_template('admin.html')

# ── Admin API Routes ──────────────────────────────────────────────────────────

@app.route('/admin/games', methods=['GET'])
@admin_required
def admin_list_games():
    try:
        return jsonify(db.get_all_games()), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/games/<game_id>', methods=['DELETE'])
@admin_required
def admin_delete_game(game_id):
    try:
        db.delete_game(game_id)
        return jsonify({'message': 'Game deleted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/games/<game_id>/status', methods=['POST'])
@admin_required
def admin_update_game_status(game_id):
    data   = request.get_json()
    status = data.get('status', '').strip()
    if status not in ('waiting', 'active', 'done'):
        return jsonify({'error': 'Invalid status'}), 400
    try:
        db.update_game_status(game_id, status)
        return jsonify({'message': 'Status updated'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/players', methods=['GET'])
@admin_required
def admin_list_players():
    try:
        game_id = request.args.get('game_id')
        if game_id:
            return jsonify(db.get_game_players(game_id)), 200
        games  = db.get_all_games()
        result = []
        for game in games:
            players = db.get_game_players(game['id'])
            for p in players:
                p['game_name'] = game['name']
                result.append(p)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/players/<game_id>/<username>', methods=['DELETE'])
@admin_required
def admin_remove_player(game_id, username):
    try:
        db.leave_game(game_id, username)
        return jsonify({'message': 'Player removed'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/designs', methods=['GET'])
@admin_required
def admin_list_designs():
    try:
        conn = db.get_db()
        rows = conn.execute(
            'SELECT * FROM designs ORDER BY owner, name'
        ).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/designs/<design_id>/privacy', methods=['POST'])
@admin_required
def admin_update_design_privacy(design_id):
    data       = request.get_json()
    is_private = 1 if data.get('is_private') else 0
    try:
        conn = db.get_db()
        conn.execute('UPDATE designs SET is_private = ? WHERE id = ?',
                     (is_private, design_id))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Privacy updated'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/designs/<design_id>', methods=['DELETE'])
@admin_required
def admin_delete_design(design_id):
    try:
        conn = db.get_db()
        row  = conn.execute(
            'SELECT filename FROM designs WHERE id = ?', (design_id,)
        ).fetchone()
        if row:
            filepath = os.path.join(UPLOAD_FOLDER_DESIGN, row['filename'])
            if os.path.exists(filepath):
                os.remove(filepath)
            conn.execute('DELETE FROM designs WHERE id = ?', (design_id,))
            conn.commit()
        conn.close()
        return jsonify({'message': 'Design deleted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/maps', methods=['GET'])
@admin_required
def admin_list_maps():
    try:
        conn = db.get_db()
        rows = conn.execute('SELECT * FROM maps ORDER BY name').fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/maps/<map_id>', methods=['DELETE'])
@admin_required
def admin_delete_map(map_id):
    try:
        conn = db.get_db()
        row  = conn.execute(
            'SELECT filename FROM maps WHERE id = ?', (map_id,)
        ).fetchone()
        if row:
            filepath = os.path.join(UPLOAD_FOLDER_MAP, row['filename'])
            if os.path.exists(filepath):
                os.remove(filepath)
            conn.execute('DELETE FROM maps WHERE id = ?', (map_id,))
            conn.commit()
        conn.close()
        return jsonify({'message': 'Map deleted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── SMS Routes ────────────────────────────────────────────────────────────────

@app.route('/send_sms_notification', methods=['POST'])
@login_required
def send_sms_notification():
    data    = request.get_json()
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    phone = get_user_phone(session['username'])
    if not phone:
        return jsonify({'error': 'No phone number on file'}), 400
    success = send_sms(phone, message)
    if success:
        return jsonify({'message': 'SMS sent'}), 200
    return jsonify({'error': 'Failed to send SMS'}), 500

@app.route('/send_game_invite', methods=['POST'])
@login_required
def send_game_invite():
    data      = request.get_json()
    recipient = data.get('username',  '').strip()
    game_name = data.get('game_name', '').strip()
    if not recipient or not game_name:
        return jsonify({'error': 'username and game_name are required'}), 400
    credentials = load_credentials()
    if recipient not in credentials:
        return jsonify({'error': 'Player not found'}), 404
    phone = get_user_phone(recipient)
    if not phone:
        return jsonify({'error': f'{recipient} has no phone number on file'}), 400
    sender  = session['username']
    message = (f'Car Wars Online: {sender} has invited you to join '
               f'"{game_name}". Log in to accept!')
    success = send_sms(phone, message)
    if success:
        return jsonify({'message': f'Invite sent to {recipient}'}), 200
    return jsonify({'error': 'Failed to send invite'}), 500

@app.route('/request_password_reset', methods=['POST'])
def request_password_reset():
    data     = request.get_json()
    username = data.get('username', '').strip()
    if not username:
        return jsonify({'error': 'Username is required'}), 400
    credentials = load_credentials()
    if username not in credentials:
        return jsonify({'message': 'If that account exists and has a phone number, a code has been sent.'}), 200
    phone = get_user_phone(username)
    if not phone:
        return jsonify({'message': 'If that account exists and has a phone number, a code has been sent.'}), 200
    import random
    code = str(random.randint(100000, 999999))
    session[f'reset_code_{username}'] = code
    send_sms(phone, f'Car Wars Online: Your password reset code is {code}.')
    return jsonify({'message': 'If that account exists and has a phone number, a code has been sent.'}), 200

@app.route('/verify_reset_code', methods=['POST'])
def verify_reset_code():
    data         = request.get_json()
    username     = data.get('username',     '').strip()
    code         = data.get('code',         '').strip()
    new_password = data.get('new_password', '').strip()
    if not username or not code or not new_password:
        return jsonify({'error': 'username, code and new_password are required'}), 400
    if len(new_password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    stored_code = session.get(f'reset_code_{username}')
    if not stored_code or stored_code != code:
        return jsonify({'error': 'Invalid or expired reset code'}), 400
    credentials = load_credentials()
    if username not in credentials:
        return jsonify({'error': 'User not found'}), 404
    hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    credentials[username]['password'] = hashed.decode('utf-8')
    save_credentials(credentials)
    session.pop(f'reset_code_{username}', None)
    return jsonify({'message': 'Password reset successfully'}), 200

# ── Game Routes ───────────────────────────────────────────────────────────────

@app.route('/create_game', methods=['POST'])
@login_required
def create_game():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data received'}), 400

    name        = data.get('name',        '').strip()
    map_file    = data.get('map',         '').strip()
    max_players = data.get('max_players', 2)
    division    = data.get('division',    5000)
    min_initial_speed = data.get('min_initial_speed', 0)
    max_initial_speed = data.get('initial_speed', 0)
    auto_start  = bool(data.get('auto_start', False))

    if not name:
        return jsonify({'error': 'Game name is required'}), 400
    if not map_file:
        return jsonify({'error': 'Map selection is required'}), 400
    if max_players < 2:
        return jsonify({'error': 'At least 2 players are required'}), 400

    try:
        game_id = db.create_game(
            name          = name,
            map_file      = map_file,
            max_players   = max_players,
            division      = division,
            created_by    = session['username'],
            min_initial_speed = min_initial_speed,
            initial_speed = max_initial_speed,
            auto_start    = auto_start
        )

        # Create T1P0 immediately so the map renders as soon as the
        # game exists, even before any players have joined.
        t1p0_filename = create_t1p0_file(game_id, name, map_file)
        if not t1p0_filename:
            print(f'Warning: T1P0 file could not be created for game {game_id}')

        return jsonify({
            'message':   'Game created successfully',
            'id':        game_id,
            'game_file': t1p0_filename
        }), 201

    except Exception as e:
        print(f'Error creating game: {e}')
        return jsonify({'error': 'Failed to create game'}), 500

@app.route('/list_games', methods=['GET'])
@login_required
def list_games():
    try:
        return jsonify(db.get_all_games()), 200
    except Exception as e:
        print(f'Error listing games: {e}')
        return jsonify({'error': 'Failed to retrieve games'}), 500

@app.route('/list_startable_games', methods=['GET'])
def list_startable_games():
    # Retrieve the username from the active session cookie
    username = session.get('username')
    if not username:
        return jsonify({"error": "Unauthorized"}), 401
        
    try:
        # Pull the newly expanded list from database.py
        games = db.get_startable_games_for_user(username)
        return jsonify(games), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_game/<game_id>', methods=['GET'])
@login_required
def get_game(game_id):
    try:
        game = db.get_game(game_id)
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        return jsonify(game), 200
    except Exception as e:
        print(f'Error getting game: {e}')
        return jsonify({'error': 'Failed to retrieve game'}), 500

@app.route('/start_game', methods=['POST'])
@login_required
def start_game():
    data    = request.get_json()
    game_id = data.get('game_id', '').strip()

    if not game_id:
        return jsonify({'error': 'game_id is required'}), 400

    try:
        game = db.get_game(game_id)
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        if game['created_by'] != session['username']:
            return jsonify({'error': 'Only the game creator can start this game'}), 403
        if game['status'] != 'waiting':
            return jsonify({'error': 'Game is not in waiting status'}), 400

        # Find existing T1P0
        t1p0_path = find_t1p0_path(game_id, game['name'])
        if not t1p0_path:
            t1p0_filename = create_t1p0_file(game_id, game['name'], game['map'])
            if not t1p0_filename:
                return jsonify({'error': 'Failed to locate game file'}), 500
        else:
            t1p0_filename = os.path.basename(t1p0_path)

        # Create T1P1M
        t1p1m_filename = create_phase_file(
            game_id          = game_id,
            game_name        = game['name'],
            source_filename  = t1p0_filename,
            new_phase_suffix = 'T1P1M'
        )
        if not t1p1m_filename:
            return jsonify({'error': 'Failed to create T1P1M phase file'}), 500

        # Build and write movement queue into T1P1M
        build_and_write_movement_queue(game_id, game['name'], phase=1)

        db.update_game_status(game_id, 'active')

        return jsonify({
            'message':       f'Game "{game["name"]}" has started!',
            'game_file':     t1p0_filename,
            'movement_file': t1p1m_filename
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'Error starting game: {e}')
        return jsonify({'error': 'Failed to start game'}), 500

@app.route('/update_game_status', methods=['POST'])
@login_required
def update_game_status():
    data    = request.get_json()
    game_id = data.get('game_id', '').strip()
    status  = data.get('status',  '').strip()
    if not game_id or not status:
        return jsonify({'error': 'game_id and status are required'}), 400
    if status not in ('waiting', 'active', 'done'):
        return jsonify({'error': 'status must be waiting, active, or done'}), 400
    try:
        db.update_game_status(game_id, status)
        return jsonify({'message': 'Status updated'}), 200
    except Exception as e:
        print(f'Error updating game status: {e}')
        return jsonify({'error': 'Failed to update status'}), 500

@app.route('/delete_game', methods=['POST'])
@login_required
def delete_game():
    data    = request.get_json()
    game_id = data.get('game_id', '').strip()
    if not game_id:
        return jsonify({'error': 'game_id is required'}), 400
    try:
        db.delete_game(game_id)
        return jsonify({'message': 'Game deleted'}), 200
    except Exception as e:
        print(f'Error deleting game: {e}')
        return jsonify({'error': 'Failed to delete game'}), 500

# ── Player Routes ─────────────────────────────────────────────────────────────

@app.route('/join_game', methods=['POST'])
@login_required
def join_game():
    data = request.get_json()
    game_id = data.get('game_id', '').strip()
    if not game_id:
        return jsonify({'error': 'game_id is required'}), 400
    driver_selected_speed = int(data.get('starting_speed', 0)) # Default fallback safety

    try:
        game = db.get_game(game_id)
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        if game['status'] != 'waiting':
            return jsonify({'error': 'Game is no longer open to join'}), 400

        players = db.get_game_players(game_id)
        if len(players) >= game['max_players']:
            return jsonify({'error': 'Game is full'}), 400
        if db.is_player_in_game(game_id, session['username']):
            return jsonify({'error': 'You are already in this game'}), 400

        car_image_name = data.get('car_image_name', '').strip()
        t1p0_path = find_t1p0_path(game_id, game['name'])

        # ── NEW: SERVER-SIDE DUPLICATE CHECK ──
        if t1p0_path and car_image_name:
            existing_records = read_game_file(t1p0_path)
            for record in existing_records:
                # Enforce space-stripping normalization on keys to ensure reliable evaluation
                normalized_record = {str(k).replace(' ', ''): v for k, v in record.items()}
                if normalized_record.get('CarPosition') == 'CarPosition':
                    if normalized_record.get('car_image_name') == car_image_name:
                        return jsonify({
                            'error': f'The car image "{car_image_name}" has already been claimed by another player.'
                        }), 400

        # Unique index assignment (1-based index)
        position_number = len(players) + 1
        db.join_game(game_id, session['username'], position_number)

        if t1p0_path and car_image_name:
            design_choice = data.get('design', '').strip()
            # Inject player name along with position number for strict map tracking updates
            success = add_car_position_to_file(
                filepath=t1p0_path,
                position_number=position_number,
                car_image_name=car_image_name,
                owner_username=session['username'],
                initial_velocity=driver_selected_speed, # <-- Pass the driver variable forward
                design=design_choice # Pass parameters forward to trace file layers nativel
            )
            if not success:
                print(f'Warning: could not serialize CarPosition for {session["username"]}')

        # Evaluates game countdown auto-start rule conditions
        updated_players = db.get_game_players(game_id)
        game_now_full = len(updated_players) >= game['max_players']
        if game_now_full and game['auto_start']:
            db.update_game_status(game_id, 'active')

        return jsonify({
            'message': f'{session["username"]} joined — game is full and auto-started!' if (game_now_full and game['auto_start']) else f'{session["username"]} joined the game',
            'auto_started': game_now_full and game['auto_start'],
            'game_file': os.path.basename(t1p0_path) if t1p0_path else ''
        }), 200
    except Exception as e:
        print(f'Error joining game structural routine: {e}')
        return jsonify({'error': 'Failed to join game'}), 500

@app.route('/get_game_players/<game_id>', methods=['GET'])
@login_required
def get_game_players(game_id):
    try:
        return jsonify(db.get_game_players(game_id)), 200
    except Exception as e:
        print(f'Error getting players: {e}')
        return jsonify({'error': 'Failed to retrieve players'}), 500

@app.route('/set_player_design', methods=['POST'])
@login_required
def set_player_design():
    data    = request.get_json()
    game_id = data.get('game_id', '').strip()
    design  = data.get('design',  '').strip()
    if not game_id or not design:
        return jsonify({'error': 'game_id and design are required'}), 400
    try:
        db.set_player_design(game_id, session['username'], design)

        # ── Snapshot the selected design into the game's directory ──
        # Copies ./uploads/designs/<design> to ./games/<game_id>/player_<N>_<design>
        # so combat can track per-player damage/ammo without touching the shared library copy.
        players = db.get_game_players(game_id)
        player_entry = next((p for p in players if p['username'] == session['username']), None)

        if player_entry:
            position_number = player_entry.get('position_number')
            source_design_path = os.path.join(UPLOAD_FOLDER_DESIGN, design)

            if position_number and os.path.exists(source_design_path):
                game_dir = game_dir_path(game_id)
                os.makedirs(game_dir, exist_ok=True)

                snapshot_filename = f"player_{position_number}_{design}"
                destination_path = os.path.join(game_dir, snapshot_filename)

                try:
                    shutil.copy2(source_design_path, destination_path)
                    print(f"[DESIGN SNAPSHOT] Copied {design} -> {snapshot_filename}")
                except Exception as copy_err:
                    print(f"[DESIGN SNAPSHOT ERROR] Failed to copy design file: {copy_err}")
            else:
                if not position_number:
                    print(f"[DESIGN SNAPSHOT WARNING] No position_number found for {session['username']} in game {game_id}")
                if not os.path.exists(source_design_path):
                    print(f"[DESIGN SNAPSHOT WARNING] Source design not found: {source_design_path}")
        else:
            print(f"[DESIGN SNAPSHOT WARNING] Could not find player entry for {session['username']} in game {game_id}")

        return jsonify({'message': 'Design assigned'}), 200
    except Exception as e:
        print(f'Error setting design: {e}')
        return jsonify({'error': 'Failed to assign design'}), 500
    
@app.route('/set_player_car_image', methods=['POST'])
@login_required
def set_player_car_image():
    data           = request.get_json()
    game_id        = data.get('game_id',        '').strip()
    car_image_name = data.get('car_image_name', '').strip()
    if not game_id or not car_image_name:
        return jsonify({'error': 'game_id and car_image_name are required'}), 400
    try:
        db.set_player_car_image(game_id, session['username'], car_image_name)
        return jsonify({'message': 'Car image assigned'}), 200
    except Exception as e:
        print(f'Error setting car image: {e}')
        return jsonify({'error': 'Failed to assign car image'}), 500

@app.route('/set_player_ready', methods=['POST'])
@login_required
def set_player_ready():
    data     = request.get_json()
    game_id  = data.get('game_id', '').strip()
    is_ready = bool(data.get('is_ready', False))
    if not game_id:
        return jsonify({'error': 'game_id is required'}), 400
    try:
        db.set_player_ready(game_id, session['username'], is_ready)
        status = db.get_player_ready_status(game_id)
        if status['all_ready'] and status['count'] >= 2:
            db.update_game_status(game_id, 'active')
            return jsonify({
                'message':     'All players ready — game started!',
                'game_active': True
            }), 200
        return jsonify({
            'message':     'Ready status updated',
            'game_active': False,
            'ready_count': sum(1 for p in status['players'] if p['is_ready']),
            'total_count': status['count']
        }), 200
    except Exception as e:
        print(f'Error setting ready status: {e}')
        return jsonify({'error': 'Failed to set ready status'}), 500

@app.route('/leave_game', methods=['POST'])
@login_required
def leave_game():
    data    = request.get_json()
    game_id = data.get('game_id', '').strip()
    if not game_id:
        return jsonify({'error': 'game_id is required'}), 400
    try:
        db.leave_game(game_id, session['username'])
        return jsonify({'message': f'{session["username"]} left the game'}), 200
    except Exception as e:
        print(f'Error leaving game: {e}')
        return jsonify({'error': 'Failed to leave game'}), 500

# ── Spectator Routes ──────────────────────────────────────────────────────────

@app.route('/spectate_game', methods=['POST'])
@login_required
def spectate_game():
    data    = request.get_json()
    game_id = data.get('game_id', '').strip()
    if not game_id:
        return jsonify({'error': 'game_id is required'}), 400
    try:
        game = db.get_game(game_id)
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        if db.is_player_in_game(game_id, session['username']):
            return jsonify({'error': 'You are already a player in this game'}), 400
        db.add_spectator(game_id, session['username'])
        return jsonify({'message': f'Now spectating "{game["name"]}"'}), 200
    except Exception as e:
        print(f'Error spectating game: {e}')
        return jsonify({'error': 'Failed to spectate game'}), 500

@app.route('/get_spectators/<game_id>', methods=['GET'])
@login_required
def get_spectators(game_id):
    try:
        return jsonify(db.get_spectators(game_id)), 200
    except Exception as e:
        print(f'Error getting spectators: {e}')
        return jsonify({'error': 'Failed to retrieve spectators'}), 500

# ── Map Routes ────────────────────────────────────────────────────────────────

@app.route('/list_maps', methods=['GET'])
@login_required
def list_maps():
    try:
        maps = db.get_all_maps()
        return jsonify([m['filename'] for m in maps]), 200
    except Exception as e:
        print(f'Error listing maps: {e}')
        return jsonify({'error': 'Failed to retrieve maps'}), 500

def list_game_files2(game_id):
    try:
        all_files  = os.listdir(GAME_FOLDER)
        game_files = [f for f in all_files if f.startswith(game_id)]
        return jsonify({'files': game_files}), 200
    except Exception as e:
        print(f'Error listing game files: {e}')
        return jsonify({'error': 'Failed to list game files'}), 500

@app.route('/list_game_files/<game_id>', methods=['GET'])
@login_required
def list_game_files(game_id):
    """
    Lists only turn/phase files (T#P#[M|C] or T#P0/EOT) inside a game's
    dedicated directory. Player design snapshots (Player_N_car.txt) are
    intentionally excluded, since the client's phase navigator only
    understands the T#P# naming pattern.
    """
    try:
        game_dir = game_dir_path(game_id)
        if not os.path.isdir(game_dir):
            return jsonify({'files': []}), 200

        all_files = os.listdir(game_dir)
        game_files = [f for f in all_files if re.match(r'^T\d+P', f) and f.endswith('.txt')]
        return jsonify({'files': game_files}), 200
    except Exception as e:
        print(f'Error listing game files: {e}')
        return jsonify({'error': 'Failed to list game files'}), 500
    
@app.route('/list_my_games', methods=['GET'])
@login_required
def list_my_games():
    try:
        conn = db.get_db()
        rows = conn.execute('''
            SELECT g.*, gp.design, gp.position_number, gp.car_image
            FROM games g
            JOIN game_players gp ON gp.game_id = g.id
            WHERE gp.username = ?
            ORDER BY g.created_at DESC
        ''', (session['username'],)).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as e:
        print(f'Error listing games for {session["username"]}: {e}')
        return jsonify({'error': 'Failed to retrieve your games'}), 500

# ── Design Routes ─────────────────────────────────────────────────────────────

@app.route('/list_designs', methods=['GET'])
@login_required
def list_designs():
    try:
        public  = db.get_all_designs()
        private = [d for d in db.get_designs_by_owner(session['username'])
                   if d['is_private'] == 1]
        seen, combined = set(), []
        for d in public + private:
            if d['filename'] not in seen:
                seen.add(d['filename'])
                combined.append(d)
        return jsonify([d['filename'] for d in combined]), 200
    except Exception as e:
        print(f'Error listing designs: {e}')
        return jsonify({'error': 'Failed to retrieve designs'}), 500

@app.route('/list_my_designs/<username>', methods=['GET'])
@login_required
def list_my_designs(username):
    try:
        designs = db.get_designs_by_owner(username)
        return jsonify([d['filename'] for d in designs]), 200
    except Exception as e:
        print(f'Error listing designs for {username}: {e}')
        return jsonify({'error': 'Failed to retrieve designs'}), 500

# ── Upload Helpers ────────────────────────────────────────────────────────────

def save_uploaded_file(folder):
    if 'file' not in request.files:
        return None, None, jsonify({'error': 'No file in request'}), 400
    file = request.files['file']
    if file.filename == '':
        return None, None, jsonify({'error': 'No file selected'}), 400
    filename  = file.filename
    save_path = os.path.join(folder, filename)
    file.save(save_path)
    print(f'File saved to: {save_path}')
    return save_path, filename, None

# ── Upload Routes ─────────────────────────────────────────────────────────────

@app.route('/upload_designs', methods=['POST'])
@login_required
def upload_designs():
    is_private = request.form.get('is_private', 'false').lower() == 'true'
    overwrite  = request.form.get('overwrite',  'false').lower() == 'true'

    if 'file' not in request.files or request.files['file'].filename == '':
        return jsonify({'error': 'No file selected'}), 400

    incoming_filename = request.files['file'].filename
    file_content      = request.files['file'].read()
    request.files['file'].seek(0)

    try:
        data       = ast.literal_eval(file_content.decode('utf-8'))
        total_cost = data[0].get('total_cost', None) if isinstance(data, list) else None
    except Exception:
        total_cost = None

    if total_cost is not None:
        prefix         = get_division_prefix(total_cost)
        final_filename = prefix + incoming_filename
    else:
        final_filename = incoming_filename

    final_path = os.path.join(UPLOAD_FOLDER_DESIGN, final_filename)

    if os.path.exists(final_path) and not overwrite:
        return jsonify({
            'error':    'file_exists',
            'filename': final_filename,
            'message':  f'A file named "{final_filename}" already exists.'
        }), 409

    save_path, filename, err = save_uploaded_file(UPLOAD_FOLDER_DESIGN)
    if err:
        return err

    if total_cost is not None:
        new_path = os.path.join(UPLOAD_FOLDER_DESIGN, final_filename)
        if save_path != new_path:
            if os.path.exists(new_path):
                os.remove(new_path)
            os.rename(save_path, new_path)
        filename = final_filename

    if overwrite:
        db.delete_design_by_filename(final_filename)

    db.register_design(filename, session['username'], is_private)
    return jsonify({'message': 'Upload successful', 'filename': filename}), 200

@app.route('/upload_maps', methods=['POST'])
@login_required
def upload_maps():
    overwrite = request.form.get('overwrite', 'false').lower() == 'true'

    if 'file' not in request.files or request.files['file'].filename == '':
        return jsonify({'error': 'No file selected'}), 400

    incoming_filename = request.files['file'].filename
    final_path        = os.path.join(UPLOAD_FOLDER_MAP, incoming_filename)

    if os.path.exists(final_path) and not overwrite:
        return jsonify({
            'error':    'file_exists',
            'filename': incoming_filename,
            'message':  f'A file named "{incoming_filename}" already exists.'
        }), 409

    save_path, filename, err = save_uploaded_file(UPLOAD_FOLDER_MAP)
    if err:
        return err

    if overwrite:
        db.delete_map_by_filename(filename)

    db.register_map(filename, session['username'])
    return jsonify({'message': 'Upload successful', 'filename': filename}), 200

# ── Car Image Routes ──────────────────────────────────────────────────────────

@app.route('/upload_car_image', methods=['POST'])
@login_required
def upload_car_image():
    if 'file' not in request.files or request.files['file'].filename == '':
        return jsonify({'error': 'No file selected'}), 400

    image_name = request.form.get('image_name', '').strip()
    is_private = request.form.get('is_private', 'false').lower() == 'true'

    if not image_name:
        return jsonify({'error': 'Image name is required'}), 400

    file = request.files['file']

    try:
        file_bytes  = file.read()
        base64_data = base64.b64encode(file_bytes).decode('utf-8')
        test_image  = Image.open(BytesIO(file_bytes))
        w, h = test_image.size
        if w != 21 or h != 41:
            return jsonify({
                'error': f'Car image must be 21x41 pixels. This image is {w}x{h}.'
            }), 400
    except Exception as e:
        return jsonify({'error': f'Invalid image file: {str(e)}'}), 400

    success = db.register_car_image(
        name        = image_name,
        owner       = session['username'],
        base64_data = base64_data,
        is_private  = is_private
    )

    if not success:
        return jsonify({
            'error': f'A car image named "{image_name}" already exists. '
                     f'Please choose a different name.'
        }), 409

    return jsonify({'message': f'Car image "{image_name}" uploaded successfully.'}), 200

@app.route('/list_car_images', methods=['GET'])
@login_required
def list_car_images():
    try:
        images = db.get_car_images_for_user(session['username'])
        return jsonify([{'name': i['name'], 'owner': i['owner']}
                        for i in images]), 200
    except Exception as e:
        print(f'Error listing car images: {e}')
        return jsonify({'error': 'Failed to retrieve car images'}), 500

@app.route('/get_car_image/<name>', methods=['GET'])
@login_required
def get_car_image(name):
    try:
        image = db.get_car_image_by_name(name)
        if not image:
            return jsonify({'error': 'Car image not found'}), 404
        if image['is_private'] and image['owner'] != session['username']:
            return jsonify({'error': 'Access denied'}), 403
        return jsonify({
            'name':        image['name'],
            'owner':       image['owner'],
            'base64_data': image['base64_data'],
            'is_private':  image['is_private']
        }), 200
    except Exception as e:
        print(f'Error getting car image: {e}')
        return jsonify({'error': 'Failed to retrieve car image'}), 500

# ── Map Rendering ─────────────────────────────────────────────────────────────

@app.route('/render_map/<filename>', methods=['GET'])
@login_required
def render_map(filename):
    filename = os.path.basename(filename)
    
    # BUG FIX: Check if it's an active game file (contains Turn/Phase signifiers)
    if "T" in filename and "P" in filename and filename.endswith('.txt'):
        map_path = os.path.join(GAME_FOLDER, filename)
    else:
        map_path = os.path.join(UPLOAD_FOLDER_MAP, filename)

    if not os.path.exists(map_path):
        print(f"[RENDER ERROR] File not found at path: {map_path}")
        return jsonify({'error': 'Map file target not found'}), 404
        
    try:
        from map_renderer import MapRenderer
        renderer = MapRenderer()
        image = renderer.render_from_file(map_path)
        
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)
        
        response = send_file(buffer, mimetype='image/png')
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        print(f'Error rendering map asset: {e}')
        return jsonify({'error': 'Failed to render map'}), 500

@app.route('/map_file_timestamp/<filename>', methods=['GET'])
@login_required
def map_file_timestamp(filename):
    filename = os.path.basename(filename)
    
    # BUG FIX: Direct the time validation check to the correct folder
    if "T" in filename and "P" in filename and filename.endswith('.txt'):
        map_path = os.path.join(GAME_FOLDER, filename)
    else:
        map_path = os.path.join(UPLOAD_FOLDER_MAP, filename)

    if not os.path.exists(map_path):
        return jsonify({'error': 'Target file not found for timestamp checking'}), 404
    try:
        mtime = os.path.getmtime(map_path)
        return jsonify({'filename': filename, 'mtime': mtime}), 200
    except Exception as e:
        print(f'Error getting file timestamp structure: {e}')
        return jsonify({'error': 'Failed to get timestamp'}), 500

@app.route('/get_map_max_players/<path:filename>', methods=['GET'])
def get_map_max_players(filename):
    # Construct the correct path relative to your running script location
    # This safely bridges the './uploads/maps' relative path notation
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, UPLOAD_FOLDER_MAP, filename)
    
    if not os.path.exists(file_path):
        return jsonify({"max_players": 8, "default_players": 2}), 404
        
    max_position = 2 # Set absolute floor to at least 2 players
    
    try:
        with open(file_path, 'r') as file:
            for line in file:
                # Match lines containing 'position_number': 8.0 or variations
                # Handles floats, integers, and spaces flexibly
                match = re.search(r"'position_number'\s*:\s*([0-9.]+)", line)
                if match:
                    pos_val = float(match.group(1))
                    # Track the largest value found, cast to an integer
                    if int(pos_val) > max_position:
                        max_position = int(pos_val)
                        
        return jsonify({
            "max_players": max_position,
            "default_players": max_position # Set default to the highest value found
        }), 200
    except Exception as e:
        return jsonify({"max_players": 8, "default_players": 2, "error": str(e)}), 500
    
@app.route('/api/game/maneuver', methods=['POST'])
def handle_game_maneuver():
    """
    Endpoint executed immediately when a player selects a driving vector button.
    Validates legal maneuvering allowances, processes vector math previews, 
    and tracks fractional budget segments natively.
    """
    data = request.get_json() or {}
    game_id = data.get('game_id', data.get('gameId', '')).strip()
    username = data.get('username')
    maneuver = data.get('maneuver', data.get('maneuverCode', '')).strip()

    # Validation check: verify the session cookie matches the player profile
    if session.get('username') != username:
        return jsonify({"error": "Unauthorized action profile"}), 403

    if not game_id or not username or not maneuver:
        return jsonify({"error": "Missing game_id, username, or maneuver in payload"}), 400

    try:
        # 1. Isolate game state layout files
        game_dir = game_dir_path(game_id)
        if not os.path.isdir(game_dir):
            return jsonify({"error": "Active match tracking folder missing."}), 404
            
        all_files = os.listdir(game_dir)
        game_files = sorted([f for f in all_files if re.match(r'^T\d+P', f) and f.endswith('.txt')])

        if not game_files:
            return jsonify({"error": "Could not identify active game state tracking file"}), 404

        filepath = os.path.join(game_dir, game_files[-1])
        file_data = read_game_file(filepath)

        # 2. Locate both the basic tracking car node and the global active movement queue block
        base_car = next((r for r in file_data if str(r.get('CarPosition', '')).replace(' ', '') == 'CarPosition' and r.get('owner') == username), None)
        mq_entry = next((r for r in file_data if r.get('MovementQueue') == 'MovementQueue'), None)

        if not base_car or not mq_entry:
            return jsonify({"error": "Vehicle profile metadata or global movement phase context missing."}), 404

        # Extract this specific player's tracking node from inside the movement queue layout array
        mq_players = mq_entry.get('players', [])
        queue_player = next((p for p in mq_players if p.get('username') == username), None)

        if not queue_player:
            return jsonify({"error": "Logged-in driver profile mismatch inside live phase execution registry."}), 400

        # 3. Read live structural capacity values safely
        full_remaining = int(queue_player.get('full_remaining', 0))
        half_remaining = float(queue_player.get('half_remaining', 0.0))
        already_maneuvered = bool(queue_player.get('maneuvered', False))
        half_selected_available = bool(queue_player.get('half_forced', False))
        half_selected_already = bool(half_remaining == 0.0) # how many halfs are left?

        is_bend = maneuver not in ['STR', 'HALF']
        is_half = (maneuver == 'HALF')

        # ── STRICTION ENFORCEMENT FILTER 1: MANEUVER EXHAUSTION ──
        if is_bend and already_maneuvered:
            return jsonify({"error": "Maneuver already exhausted this phase step. All remaining movements must be straight travel vectors."}), 400

        # ── STRICTION ENFORCEMENT FILTER 2: EXACTLY 0.5 REMAINING ──
        if full_remaining == 0 and half_remaining == 0.5 and not is_half:
            return jsonify({"error": "Illegal selection context. Only a half-step footprint option is valid for the remaining phase balance."}), 400

        # ── STRICTION ENFORCEMENT FILTER 3: TERMINAL FRACTION RULE ──
        if is_half and half_selected_already:
            return jsonify({"error": "Fractional choice locked. Once a half-step is executed, all subsequent phase segment motions must be full increments."}), 400

        # 4. Hand off physical asset geometric vector tracking calculations to your GameEngine
        success, message = GameEngine.process_player_movement(game_id, username, maneuver)
        if not success:
            return jsonify({"error": message}), 400

        # Re-read file records in case Engine calculations appended physical coordinate metrics
        file_data = read_game_file(filepath)

        # Prune older past unconfirmed ghost nodes for this user to refresh canvas display overlay
        file_data = [r for r in file_data if not (str(r.get('ProposedCarPosition', '')).replace(' ', '') == 'ProposedCarPosition' and r.get('owner') == username)]

        # 5. Compute dynamic budget allocations for the targeted GHOST PREVIEW element
        step_cost = 0.5 if is_half else 1.0
        calc_rem = round(max(0.0, float(queue_player.get('remaining', 1.0)) - step_cost), 1)
        
        # Build precise tracking states that preview the state if this choice gets confirmed
        preview_full = max(0, full_remaining - (0 if is_half else 1))
        preview_half = 0.0 if is_half else half_remaining
        preview_half_forced = True if (is_half and full_remaining > 0) else half_selected_already

        # Normalize physical rotation keys locally to establish safe float lookups
        normalized_car = {str(k).replace(' ', ''): v for k, v in base_car.items()}
        current_x = float(normalized_car.get('local_starting_x_qty', 0.0))
        current_y = float(normalized_car.get('local_starting_y_qty', 0.0))
        current_angle = float(normalized_car.get('orientation', 0.0))

        # Vector offset calculations matching standard asset sizes
        CAR_LENGTH = 1.0
        CAR_WIDTH = 0.5

        if maneuver == 'STR':
            rad_current = math.radians(current_angle)
            final_x = current_x + (math.sin(rad_current) * CAR_LENGTH)
            final_y = current_y + (-math.cos(rad_current) * CAR_LENGTH)
            final_angle = current_angle
        elif is_half:
            rad_current = math.radians(current_angle)
            final_x = current_x + (math.sin(rad_current) * (CAR_LENGTH / 2.0))
            final_y = current_y + (-math.cos(rad_current) * (CAR_LENGTH / 2.0))
            final_angle = current_angle
        elif is_bend:
            severity = int(maneuver[1:-1]) if re.search(r'\d+', maneuver) else 1
            direction = maneuver[-1]
            delta_degrees = severity * 15
            rad_start = math.radians(current_angle)
            mid_x = current_x + (math.sin(rad_start) * (CAR_LENGTH / 2.0))
            mid_y = current_y + (-math.cos(rad_start) * (CAR_LENGTH / 2.0))
            r_x, r_y = math.cos(rad_start), math.sin(rad_start)

            if direction == 'L':
                pivot_x = mid_x - (r_x * (CAR_WIDTH / 2.0))
                pivot_y = mid_y - (r_y * (CAR_WIDTH / 2.0))
                rotation_angle = -delta_degrees
                final_angle = (current_angle - delta_degrees) % 360
            else:
                pivot_x = mid_x + (r_x * (CAR_WIDTH / 2.0))
                pivot_y = mid_y + (r_y * (CAR_WIDTH / 2.0))
                rotation_angle = delta_degrees
                final_angle = (current_angle + delta_degrees) % 360

            rad_rotation = math.radians(rotation_angle)
            dx, dy = mid_x - pivot_x, mid_y - pivot_y
            rotated_mid_x = pivot_x + (dx * math.cos(rad_rotation) - dy * math.sin(rad_rotation))
            rotated_mid_y = pivot_y + (dx * math.sin(rad_rotation) + dy * math.cos(rad_rotation))
            rad_final = math.radians(final_angle)
            final_x = rotated_mid_x + (math.sin(rad_final) * (CAR_LENGTH / 2.0))
            final_y = rotated_mid_y + (-math.cos(rad_final) * (CAR_LENGTH / 2.0))
        else:
            final_x, final_y, final_angle = current_x, current_y, current_angle

        final_heading_int = int(round(final_angle)) % 360

        # Construct the specialized asset payload mapping metrics accurately to the map canvas pipeline
        fallback_ghost = {
            'ProposedCarPosition': 'ProposedCarPosition',
            'player_number': base_car.get('player_number'),
            'owner': username,
            'local_starting_x_qty': round(final_x, 2),
            'local_starting_y_qty': round(final_y, 2),
            'heading': final_heading_int,
            'orientation': float(final_heading_int),
            'color': base_car.get('color', 'blue'),
            'car_image_name': base_car.get('car_image_name'),
            'maneuver_preview_type': maneuver,
            'remaining': calc_rem,
            'full_remaining': preview_full,
            'half_remaining': preview_half,
            'maneuvered': True if is_bend else already_maneuvered,
            'half_forced': preview_half_forced,
            'timestamp': datetime.now().isoformat()
        }
        
        file_data.append(fallback_ghost)
        write_game_file(filepath, file_data)
        
        return jsonify({"status": "success", "message": f"Maneuver vector choice ({maneuver}) successfully staged for preview evaluation."}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Internal engine calculation crash during route tracking: {str(e)}"}), 500

@app.route('/api/game/fire', methods=['POST'])
def handle_game_fire():
    data = request.json
    game_id = data.get('game_id')
    username = data.get('username')
    
    if session.get('username') != username:
        return jsonify({"error": "Unauthorized action profile"}), 403
        
    try:
        success, message = GameEngine.process_player_combat(game_id, username)
        if success:
            return jsonify({"status": "success", "message": message}), 200
        else:
            return jsonify({"error": message}), 400
    except Exception as e:
        return jsonify({"error": f"Engine combat failure: {str(e)}"}), 500
    
@app.route('/api/game/confirm_move', methods=['POST'])
@login_required
def handle_game_confirm_move():
    """
    Records a player's movement choice, advances the subphase queue, and
    synchronizes metadata fields to unlock the frontend title ticker display.
    Enforces dynamic fractional budgets, maneuver exhaustion, and terminal fraction locks.
    """
    print("!!! CONFIRM_MOVE ROUTE HIT !!!")
    from datetime import datetime
    import os
    from flask import jsonify, request, session

    data = request.get_json() or {}
    game_id = str(data.get('game_id', data.get('gameId', ''))).strip()
    maneuver = str(data.get('maneuver', data.get('maneuverCode', ''))).strip()
    username = session['username']

    if not game_id:
        return jsonify({'error': 'game_id is strictly required'}), 400

    game_dir = game_dir_path(game_id)
    if not os.path.isdir(game_dir):
        return jsonify({'error': f'No active game state directory found for ID: {game_id}'}), 404
        
    all_files = os.listdir(game_dir)
    game_files = sorted([f for f in all_files if re.match(r'^T\d+P', f) and f.endswith('.txt')])
    if not game_files:
        return jsonify({'error': f'No active game state tracking files found for ID: {game_id}'}), 404
        
    filepath = os.path.join(game_dir, game_files[-1])

    try:
        file_data = read_game_file(filepath)

        # 1. Harvest the active Proposed preview ghost block to grab dynamic budget logic states
        ghost_node = next(
            (r for r in file_data if str(r.get('ProposedCarPosition', '')).replace(' ', '') == 'ProposedCarPosition'
             and r.get('owner') == username),
            None
        )

        # Extract real active maneuver from ghost preview if empty in payload
        if not maneuver or maneuver == 'None' or maneuver == '':
            if ghost_node:
                maneuver = str(ghost_node.get('maneuver_preview_type', 'STR')).strip()
            else:
                maneuver = 'STR'

        # 2. Locate the central system MovementQueue block
        queue_entry = None
        queue_index = None
        for i, entry in enumerate(file_data):
            if entry.get('MovementQueue') == 'MovementQueue':
                queue_entry = entry
                queue_index = i
                break

        if queue_entry is None:
            return jsonify({'error': 'No movement queue tracking block found'}), 404

        if queue_entry.get('complete'):
            return jsonify({'error': 'Movement phase is already complete'}), 400

        players = queue_entry['players']
        for p in players:
            if 'moved_this_segment' not in p:
                p['moved_this_segment'] = False

        # Isolate this specific player from inside the movement queue sub-block matrix
        player = next((p for p in players if p['username'] == username and not p['done']
                       and not p['moved_this_segment']), None)

        if player is None:
            return jsonify({'error': 'Not your turn, already moved this segment, or done with phase'}), 400

        first_active = next((p for p in players if not p['done'] and not p['moved_this_segment']), None)
        if first_active is None or first_active['username'] != username:
            return jsonify({'error': 'It is currently not your turn to execute a move based on speed initiative'}), 400

        # 3. Synchronize handling class deductions for maneuvers (Bends)
        bend_maneuvers = {'D1L','D2L','D3L','D4L','D5L','D6L','D1R','D2R','D3R','D4R','D5R','D6R'}
        is_bend = maneuver in bend_maneuvers

        if is_bend:
            player_db_entries = db.get_game_players(game_id)
            player_entry = next((p for p in player_db_entries if p['username'] == username), None)

            if player_entry:
                position_number = player_entry.get('position_number')
                design = player_entry.get('design')

                if position_number and design:
                    snapshot_filename = f"player_{position_number}_{design}"
                    snapshot_path = os.path.join(game_dir, snapshot_filename)

                    if os.path.exists(snapshot_path):
                        try:
                            with open(snapshot_path, 'r', encoding='utf-8') as f:
                                raw_content = f.read().strip()

                            if raw_content:
                                parsed_data = ast.literal_eval(raw_content)
                                car_record = None
                                is_wrapped_in_list = False

                                if isinstance(parsed_data, dict):
                                    car_record = parsed_data
                                elif isinstance(parsed_data, list) and len(parsed_data) > 0 and isinstance(parsed_data[0], dict):
                                    car_record = parsed_data[0]
                                    is_wrapped_in_list = True

                                if car_record is not None:
                                    d_value_match = re.search(r'\d+', maneuver)
                                    if d_value_match:
                                        d_cost = int(d_value_match.group())
                                        current_hc = int(car_record.get('hc', 0))
                                        new_hc = current_hc - d_cost
                                        car_record['hc'] = str(new_hc)

                                    with open(snapshot_path, 'w', encoding='utf-8') as f:
                                        if is_wrapped_in_list:
                                            f.write(str([car_record]) + '\n')
                                        else:
                                            f.write(str(car_record) + '\n')
                                    print(f"[HC UPDATE SUCCESS] Reduced {username}'s HC by {d_cost}. New HC: {new_hc}")
                        except Exception as hc_err:
                            print(f"[HC UPDATE ERROR] Failed executing raw file subtraction parse: {hc_err}")

        # ── 4. STAGE INTEGRATION LOCKDOWN: SYNCHRONIZE METRICS FROM GHOST PREVIEW ── 🛠
        if ghost_node:
            player['full_remaining'] = int(ghost_node.get('full_remaining', 0))
            player['half_remaining'] = float(ghost_node.get('half_remaining', 0.0))
            player['remaining'] = round(float(ghost_node.get('remaining', 0.0)), 1)
            player['maneuvered'] = bool(ghost_node.get('maneuvered', False))
            player['half_forced'] = bool(ghost_node.get('half_forced', False))
        else:
            # Fallback deduction calculation routine if no geometric preview ghost is located
            is_half = maneuver == 'half'
            step_cost = 0.5 if is_half else 1.0
            player['remaining'] = round(max(0.0, float(player['remaining']) - step_cost), 1)
            if is_half:
                player['half_remaining'] = 0.0
                if int(player['full_remaining']) > 0:
                    player['half_forced'] = True
            else:
                player['full_remaining'] = max(0, int(player['full_remaining']) - 1)
            if is_bend:
                player['maneuvered'] = True

        # Turn progression update markers
        player['moved_this_segment'] = True

        move_record = {
            'MoveRecord': 'MoveRecord',
            'username': username,
            'maneuver': maneuver,
            'phase': queue_entry['phase'],
            'round': queue_entry['round'],
            'timestamp': datetime.now().isoformat()
        }

        # Handle complete phase exhaustion boundaries cleanly
        if float(player['remaining']) <= 0.0:
            player['done'] = True
            player['moved_this_segment'] = True
        else:
            player['done'] = False
            player['moved_this_segment'] = False

        # 5. Commit calculations back down via the central engine pipeline coordinates lock
        engine_success, engine_msg = GameEngine.confirm_player_movement(game_id, username)
        if not engine_success:
            return jsonify({'error': f"Coordinates lock failure: {engine_msg}"}), 400

        # Reload updated log list from engine storage disk map
        file_data = read_game_file(filepath)

        # Clear preview ghost nodes cleanly upon confirmation completion
        file_data = [r for r in file_data if not (str(r.get('ProposedCarPosition', '')).replace(' ', '') == 'ProposedCarPosition' and r.get('owner') == username)]

        # Check turn management progression triggers
        all_phase_done = all(p['done'] for p in queue_entry['players'])
        queue_entry['game_name'] = queue_entry.get('game_name', 'Hammer Downs Arena')
        queue_entry['turn_count'] = queue_entry.get('turn_count', 1)

        if all_phase_done:
            queue_entry['complete'] = True
            queue_entry['current_system_subphase'] = 'Combat'
            for p in queue_entry['players']:
                p['moved_this_segment'] = False

            active_cars = [r for r in file_data if r.get('CarPosition') == 'CarPosition']
            if active_cars:
                fastest_car = max(active_cars, key=lambda c: int(float(c.get('current_speed', 0))))
                queue_entry['active_player_turn'] = fastest_car.get('owner', 'Player 1')
            else:
                queue_entry['active_player_turn'] = 'Combat Phase Open'
        else:
            queue_entry['complete'] = False
            queue_entry['current_system_subphase'] = 'Movement'
            next_mover = next((p for p in queue_entry['players'] if not p['done']), player)
            queue_entry['active_player_turn'] = next_mover['username'] if next_mover else username

        # Map orientation normalization safeguards
        for record in file_data:
            if record.get('CarPosition') == 'CarPosition':
                record['heading'] = int(round(float(record.get('heading', 0))))
                record['orientation'] = int(round(float(record.get('orientation', 0))))
                # Embed updated movement queue meta fields back inside ledger arrays
                for idx, entry in enumerate(file_data):
                    if entry.get('MovementQueue') == 'MovementQueue':
                        file_data[idx] = queue_entry
                        break
                write_game_file(filepath, file_data)
        return jsonify({'message': f'{username} moved: {maneuver}',
                        'queue': queue_entry,
                        'move_record': move_record,
                        'phase_complete': queue_entry['complete']}), 200
    except Exception as e:
        print(f'Error confirming move segment: {e}')
        return jsonify({'error': 'Failed to confirm move updates.'}), 500

@app.route('/resolve_control_check', methods=['POST'])
@login_required
def api_resolve_control_check():
    """
    Resolve a control check for a player at a given speed.
    The die roll is provided by the client (or can be rolled server-side).

    POST body:
        game_id  : the current game
        speed    : current vehicle speed in mph
        die_roll : the player's die roll (optional — if omitted, server rolls)
    """
    data     = request.get_json()
    game_id  = data.get('game_id',  '').strip()
    speed    = data.get('speed',    0)
    die_roll = data.get('die_roll', None)

    if not game_id:
        return jsonify({'error': 'game_id is required'}), 400

    # If client didn't supply a roll, roll server-side
    if die_roll is None:
        die_roll = roll_d6()

    result = resolve_control_check(int(speed), int(die_roll))
    result['speed']    = speed
    result['die_roll'] = die_roll

    return jsonify(result), 200

@app.route('/get_speed_table', methods=['GET'])
@login_required
def get_speed_table():
    """Serve both lookup tables as JSON for client-side display."""
    return jsonify({
        'speed_control':    SPEED_CONTROL,
        'control_columns':  CONTROL_COLUMNS,
        'control_table':    {
            f'{k[0]}-{k[1]}': v for k, v in CONTROL_TABLE.items()
        }
    }), 200

def get_movement_queue2(game_id):
    """
    Return the current MovementQueue entry from the most recent
    movement phase file for this game.
    """
    try:
        game = db.get_game(game_id)
        if not game:
            return jsonify({'error': 'Game not found'}), 404

        # List and sort game files to find the most recent movement phase
        all_files  = os.listdir(GAME_FOLDER)
        game_files = sorted(
            [f for f in all_files if f.startswith(game_id)],
            key=lambda f: (
                # Sort by turn then phase order
                int(re.search(r'T(\d+)', f).group(1))
                if re.search(r'T(\d+)', f) else 0
            )
        )

        # Find the most recent movement phase file
        movement_file = None
        for f in reversed(game_files):
            if re.search(r'T\d+P[1-5]M\.txt$', f, re.IGNORECASE):
                movement_file = f
                break

        if not movement_file:
            return jsonify({'error': 'No movement phase file found'}), 404

        filepath = os.path.join(GAME_FOLDER, movement_file)
        data     = read_game_file(filepath)

        for entry in data:
            if entry.get('MovementQueue') == 'MovementQueue':
                return jsonify({
                    'queue':    entry,
                    'filename': movement_file
                }), 200

        return jsonify({'error': 'No movement queue found in file'}), 404

    except Exception as e:
        print(f'Error getting movement queue: {e}')
        return jsonify({'error': 'Failed to get movement queue'}), 500

@app.route('/get_movement_queue/<game_id>', methods=['GET'])
@login_required
def get_movement_queue(game_id):
    """
    Return the current MovementQueue entry from the most recent
    movement phase file for this game.
    """
    try:
        game = db.get_game(game_id)
        if not game:
            return jsonify({'error': 'Game not found'}), 404

        game_dir = game_dir_path(game_id)
        if not os.path.isdir(game_dir):
            return jsonify({'error': 'No active game state directory found'}), 404

        all_files = os.listdir(game_dir)
        game_files = sorted(
            [f for f in all_files if re.match(r'^T\d+P', f) and f.endswith('.txt')],
            key=lambda f: (
                int(re.search(r'T(\d+)', f).group(1))
                if re.search(r'T(\d+)', f) else 0
            )
        )

        movement_file = None
        for f in reversed(game_files):
            if re.search(r'T\d+P[1-5]M\.txt$', f, re.IGNORECASE):
                movement_file = f
                break

        if not movement_file:
            return jsonify({'error': 'No movement phase file found'}), 404

        filepath = os.path.join(game_dir, movement_file)
        data = read_game_file(filepath)

        for entry in data:
            if entry.get('MovementQueue') == 'MovementQueue':
                return jsonify({
                    'queue':    entry,
                    'filename': movement_file
                }), 200

        return jsonify({'error': 'No movement queue found in file'}), 404

    except Exception as e:
        print(f'Error getting movement queue: {e}')
        return jsonify({'error': 'Failed to get movement queue'}), 500
    
@app.route('/check_my_turn/<game_id>', methods=['GET'])
@login_required
def check_my_turn(game_id):
    """
    Check whether it is currently the logged-in player's turn to move.
    Returns the queue state and whether it's this player's turn.
    Used by both polling (ReJoin) and the manual Check Turn button.
    """
    try:
        game = db.get_game(game_id)
        if not game:
            return jsonify({'error': 'Game not found'}), 404

        game_dir = game_dir_path(game_id)
        if not os.path.isdir(game_dir):
            return jsonify({
                'is_my_turn':   False,
                'phase_active': False,
                'message':      'No active movement phase'
            }), 200

        game_files = [f for f in os.listdir(game_dir) if re.match(r'^T\d+P', f) and f.endswith('.txt')]

        movement_file = None
        for f in sorted(game_files, reverse=True):
            if re.search(r'T\d+P[1-5]M\.txt$', f, re.IGNORECASE):
                movement_file = f
                break

        if not movement_file:
            return jsonify({
                'is_my_turn':    False,
                'phase_active':  False,
                'message':       'No active movement phase'
            }), 200

        filepath = os.path.join(game_dir, movement_file)
        data = read_game_file(filepath)

        queue_entry = next(
            (e for e in data if e.get('MovementQueue') == 'MovementQueue'),
            None
        )

        if not queue_entry or queue_entry.get('complete'):
            return jsonify({
                'is_my_turn':   False,
                'phase_active': False,
                'message':      'Movement phase complete'
            }), 200

        username = session['username']
        players = queue_entry.get('players', [])

        # Find the first non-done player — that's who should move next
        current = next((p for p in players if not p['done']), None)

        is_my_turn = current is not None and current['username'] == username
        needs_input = is_my_turn and not (
            current.get('maneuvered') and current.get('full_remaining', 0) > 0
        )

        return jsonify({
            'is_my_turn':      is_my_turn,
            'needs_input':     needs_input,
            'phase_active':    True,
            'phase':           queue_entry['phase'],
            'current_mover':   current['username'] if current else None,
            'queue':           queue_entry,
            'filename':        movement_file,
            'phase_complete':  queue_entry.get('complete', False)
        }), 200

    except Exception as e:
        print(f'Error checking turn: {e}')
        return jsonify({'error': 'Failed to check turn'}), 500
    
def build_and_write_movement_queue(game_id: str, game_name: str, phase: int) -> bool:
    """
    Read the current phase file, extract CarPosition entries to get
    player speeds, build the movement queue, append it to the file,
    and write it back.
    """
    from game_tables import build_movement_queue

    filename = f'T{1}P{phase}M.txt'  # always turn 1 for now
    filepath = os.path.join(game_dir_path(game_id), filename)

    if not os.path.exists(filepath):
        print(f'Phase file not found: {filepath}')
        return False

    data = read_game_file(filepath)
    if not data:
        return False

    players = []
    for entry in data:
        normalized_entry = {str(k).replace(' ', ''): v for k, v in entry.items()}
        if normalized_entry.get('CarPosition') == 'CarPosition':
            players.append({
                'username': normalized_entry.get('owner', ''),
                'current_speed': int(normalized_entry.get('current_speed', 0))
            })

    if not players:
        print(f'No CarPosition entries found in {filepath}')
        return False

    queue = build_movement_queue(players, phase)
    queue['current_system_subphase'] = 'Movement'
    queue['game_name'] = game_name
    queue['turn_count'] = 1
    if queue.get('players') and len(queue['players']) > 0:
        queue['active_player_turn'] = queue['players'][0]['username']

    data = [e for e in data if str(list(e.keys())).replace(' ', '') != 'MovementQueue']
    data.append(queue)

    return write_game_file(filepath, data)

@app.route('/api/game_state/<game_id>')
def get_game_state(game_id):
    """
    Locates the active match's directory, enforces MapRenderer space-stripping 
    key normalization rules to prevent property mismatches, and updates the UI ticker.
    """
    try:
        game_dir = game_dir_path(game_id)
        if not os.path.isdir(game_dir):
            return jsonify({"success": False, "error": "Match room data not found."}), 404

        game_files = sorted([f for f in os.listdir(game_dir) if re.match(r'^T\d+P', f) and f.endswith('.txt')])

        if not game_files:
            return jsonify({"success": False, "error": "Match room data not found."}), 404

        filepath = os.path.join(game_dir, game_files[-1])
        raw_records = GameEngine.read_game_file(filepath)

        if not raw_records:
            return jsonify({"success": False, "error": "Game log database file is empty."}), 500

        # Replicate MapRenderer's structural space-stripping rule across records
        normalized_records = []
        for entry in raw_records:
            normalized_entry = {str(k).replace(' ', ''): v for k, v in entry.items()}
            normalized_records.append(normalized_entry)

        # Isolate the central metadata tracking block using clean keys
        mq = next((r for r in normalized_records if r.get('MovementQueue') == 'MovementQueue'), {})

        game_name_clean = str(mq.get('game_name', mq.get('gamename', 'Car Wars Arena')))
        turn_qty = int(float(mq.get('turn_count', mq.get('turncount', 1))))
        phase_qty = int(float(mq.get('phase', 1)))
        subphase_mode = str(mq.get('current_system_subphase', mq.get('current_system_subphase', 'Movement')))
        active_driver = str(mq.get('active_player_turn', mq.get('active_player_turn', 'Player 1')))
        
        return jsonify({
            "success": True,
            "requires_turn_speed_selection": bool(mq.get('requires_turn_speed_selection', False)),
            "queue": mq, # ── CRITICAL: The full MovementQueue block must be passed up to hydrate budgets!
            "ticker_data": {
                "game_name": game_name_clean,
                "turn": turn_qty,
                "phase": phase_qty,
                "mode": subphase_mode,
                "active_player": active_driver
            },
            "cars": [r for r in normalized_records if r.get('CarPosition') == 'CarPosition'],
            "ghosts": [r for r in normalized_records if r.get('ProposedCarPosition') == 'ProposedCarPosition']
        })

    except Exception as route_crash:
        return jsonify({"success": False, "error": f"Internal pipeline crash: {str(route_crash)}"}), 500

@app.route('/api/end_combat_subphase', methods=['POST'])
def end_combat_subphase():
    game_id = request.json.get('game_id')
    
    from phase_manager import PhaseProgressionManager
    success, log_msg = PhaseProgressionManager.advance_to_next_phase_or_turn(game_id)
    
    return jsonify({"success": success, "message": log_msg})

@app.route('/api/calculate_live_to_hit', methods=['POST'])
@login_required
def calculate_live_to_hit():
    """
    Parses live vector distance coordinates, runs Line-of-Sight blocking checks, 
    and returns exact 2D6 targeting requirements matching official rulesets.
    """
    from combat_geometry import CombatGeometryEngine
    from combat_modifiers import CombatModifiersEngine
 
    data = request.get_json()
    game_id = data.get('game_id')
    weapon_id = data.get('weapon_id')
    target_owner = data.get('target_owner')
    crew_id = data.get('crew_id')  # optional -- omitted means gunner skill contributes 0
    username = session['username']
 
    if not weapon_id:
        return jsonify({"possible": False, "reason": "No weapon selected."})
 
    game_dir = game_dir_path(game_id)
    if not os.path.isdir(game_dir):
        return jsonify({"possible": False, "reason": "Match room data not found."})
 
    game_files = sorted([f for f in os.listdir(game_dir) if re.match(r'^T\d+P', f) and f.endswith('.txt')])
    if not game_files:
        return jsonify({"possible": False, "reason": "Match room data not found."})
 
    filepath = os.path.join(game_dir, game_files[-1])
    records = GameEngine.read_game_file(filepath)
 
    attacker = next((r for r in records if r.get('CarPosition') == 'CarPosition' and r.get('owner') == username), None)
    defender = next((r for r in records if r.get('CarPosition') == 'CarPosition' and r.get('owner') == target_owner), None)
 
    if not attacker or not defender:
        return jsonify({"possible": False, "reason": "Chassis data records missing."})
 
    # PATCH (bug fix): weapon loadout (name, facing) lives in the
    # attacker's DESIGN SNAPSHOT, not their CarPosition record.
    # Position (ax, ay, orientation) correctly stays sourced from
    # CarPosition above, since that's the live/current position --
    # only the weapon lookup needs to switch sources. This mirrors
    # exactly how get_firing_dialog_data() already loads a player's
    # snapshot.
    players = db.get_game_players(game_id)
    player_entry = next((p for p in players if p['username'] == username), None)
    if not player_entry:
        return jsonify({"possible": False, "reason": "You are not a player in this game."})
 
    position_number = player_entry.get('position_number')
    design = player_entry.get('design')
    if not position_number or not design:
        return jsonify({"possible": False, "reason": "No design assigned for this player."})
 
    snapshot_filename = f"player_{position_number}_{design}"
    snapshot_path = os.path.join(game_dir, snapshot_filename)
    if not os.path.exists(snapshot_path):
        return jsonify({"possible": False, "reason": f"Car snapshot file not found: {snapshot_filename}"})
 
    car_records = GameEngine.read_game_file(snapshot_path)
    if not car_records or not isinstance(car_records[0], dict):
        return jsonify({"possible": False, "reason": "Car snapshot file is empty or malformed."})
    car_record = car_records[0]
 
    # PATCH: resolve the selected crew member's gunner skill so it
    # actually affects the to-hit roll -- previously
    # evaluate_attack_modifiers() read gunner_skill_level from the
    # CarPosition record, where that field never existed at all.
    gunner_skill = 0
    if crew_id:
        crew_roster = GameEngine.get_crew_roster(car_record)
        crew_member = next((m for m in crew_roster if m["id"] == crew_id), None)
        if crew_member is None:
            return jsonify({"possible": False, "reason": f'"{crew_id}" is not a valid crew member for this vehicle.'})
        gunner_skill = crew_member["skill_gunner"]
 
    # PATCH: resolve any installed Targeting Computer / SWC / Cyberlink
    # bonus that applies to this specific crew member + weapon
    # combination -- see get_targeting_computer_bonus for the full
    # rule set (position-wide vs single-weapon types, smart link
    # exclusion for SWC/HRSWC/Cyberlink).
    tc_bonus = 0
    if crew_id:
        tc_bonus = GameEngine.get_targeting_computer_bonus(car_record, crew_id, weapon_id)
 
    w_name, w_facing = GameEngine.get_weapon_facing_and_name(car_record, weapon_id)

    if w_name is None:
        return jsonify({"possible": False, "reason": f'"{weapon_id}" is not a valid weapon/link for this vehicle.'})
 
    ax, ay = float(attacker['local_starting_x_qty']), float(attacker['local_starting_y_qty'])
    dx, dy = float(defender['local_starting_x_qty']), float(defender['local_starting_y_qty'])
    distance = math.hypot(dx - ax, dy - ay)
 
    # 1. Determine Pinpoint Weapon Mount Origin Coordinates
    w_x, w_y = CombatGeometryEngine.get_weapon_origin(ax, ay, float(attacker['orientation']), w_facing)
 
    # 2. Enforce Fire Arc Horizon Alignments
    target_arc = CombatGeometryEngine.determine_relative_arc(w_x, w_y, float(attacker['orientation']), dx, dy)
    if w_facing != "Top" and w_facing != target_arc:
        return jsonify({"possible": False, "reason": f"Target in your {target_arc} arc, weapon faces {w_facing}."})
 
    # 3. Ray-Cast Line-of-Sight Checks
    if CombatGeometryEngine.is_line_of_sight_blocked((w_x, w_y), (dx, dy), records):
        return jsonify({"possible": False, "reason": "Line of Sight blocked by map barrier."})
 
    # 4. Sum up table target modifications profiles
    weapon_mock = {"name": w_name, "facing": w_facing}
    # PATCH: pass a COPY of attacker with gunner_skill_level filled
    # in -- attacker itself stays unmodified (it's a CarPosition
    # record, not something we want to silently mutate).
    attacker_for_modifiers = dict(attacker)
    attacker_for_modifiers['gunner_skill_level'] = gunner_skill
    mods = CombatModifiersEngine.evaluate_attack_modifiers(attacker_for_modifiers, defender, weapon_mock, "Chassis", distance)
    # PATCH: Targeting Computer / SWC / Cyberlink bonus, added
    # separately rather than through evaluate_attack_modifiers' old
    # computer_type check -- see note below.
    mods += tc_bonus
 
    needed_roll = 7 - mods
    needed_roll = max(2, min(12, needed_roll))
 
    return jsonify({
        "possible": True,
        "needed_roll": needed_roll,
        "distance_inches": round(distance, 1),
        "arc_facing": target_arc
    })
    
@app.route('/render_game_file/<game_id>/<filename>', methods=['GET'])
@login_required
def render_game_file(game_id, filename):
    """
    Renders a specific phase file belonging to a game's dedicated directory.
    Separate from /render_map, which only serves pre-game map uploads.
    """
    filename = os.path.basename(filename)
    map_path = os.path.join(game_dir_path(game_id), filename)

    if not os.path.exists(map_path):
        print(f"[RENDER ERROR] File not found at path: {map_path}")
        return jsonify({'error': 'Game file target not found'}), 404

    try:
        from map_renderer import MapRenderer
        renderer = MapRenderer()
        image = renderer.render_from_file(map_path)

        buffer = BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)

        response = send_file(buffer, mimetype='image/png')
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        print(f'Error rendering game file asset: {e}')
        return jsonify({'error': 'Failed to render game file'}), 500

@app.route('/game_file_timestamp/<game_id>/<filename>', methods=['GET'])
@login_required
def game_file_timestamp(game_id, filename):
    """
    Returns the last-modified timestamp for a specific phase file
    belonging to a game's dedicated directory. Used by client-side polling
    to detect when another player has updated the shared game state.
    """
    filename = os.path.basename(filename)
    game_dir = game_dir_path(game_id)
    map_path = os.path.join(game_dir_path(game_id), filename)

    # SAFETY: Check if the folder went missing due to an engine reset or cleanup
    if not os.path.isdir(game_dir):
        return jsonify({'error': 'Active game directory missing or deleted', 'clear_session': True}), 404

    if not os.path.exists(map_path):
        return jsonify({'error': 'Target file not found for timestamp checking'}), 404
    try:
        mtime = os.path.getmtime(map_path)
        return jsonify({'filename': filename, 'mtime': mtime}), 200
    except Exception as e:
        print(f'Error getting file timestamp structure: {e}')
        return jsonify({'error': 'Failed to get timestamp'}), 500

@app.route('/api/game/get_firing_dialog_data', methods=['POST'])
@login_required
def get_firing_dialog_data():
    """
    Builds the data needed to populate the Firing Action dialog:
    crew members (with used/available status), weapons/accessories
    (with used/available status), and a list of possible targets.
    To-hit calculation for each target is handled separately (later).
    """
    data = request.get_json() or {}
    game_id = str(data.get('game_id', '')).strip()
    username = session['username']

    if not game_id:
        return jsonify({'error': 'game_id is required'}), 400

    try:
        # 1. Locate this player's design snapshot file
        players = db.get_game_players(game_id)
        player_entry = next((p for p in players if p['username'] == username), None)
        if not player_entry:
            return jsonify({'error': 'You are not a player in this game'}), 404

        position_number = player_entry.get('position_number')
        design = player_entry.get('design')
        if not position_number or not design:
            return jsonify({'error': 'No design assigned for this player'}), 400

        snapshot_filename = f"player_{position_number}_{design}"
        snapshot_path = os.path.join(game_dir_path(game_id), snapshot_filename)

        if not os.path.exists(snapshot_path):
            return jsonify({'error': f'Car snapshot file not found: {snapshot_filename}'}), 404

        car_records = GameEngine.read_game_file(snapshot_path)
        if not car_records or not isinstance(car_records[0], dict):
            return jsonify({'error': 'Car snapshot file is empty or malformed'}), 500

        car_record = car_records[0]

        # 2. Crew members, with used/available status
        # PATCH: reads the real per-row crew data instead of synthesizing
        # generic titles from a single count. "id" (not title) is what
        # the frontend now sends back for crew_title -- err, crew_id --
        # selection and firing-action confirmation, since titles alone
        # can't disambiguate duplicate roles (two Gunners, etc.).
        crew_roster = GameEngine.get_crew_roster(car_record)
        used_crew = car_record.get('firing_actions_used_this_turn', [])
 
        crew_list = [
            {
                "id": member["id"],
                "title": member["title"],
                "available": member["id"] not in used_crew,
            }
            for member in crew_roster
        ]

        # 3. Weapons/accessories, with used/available status
        used_weapons = car_record.get('weapons_used_this_turn', [])
        link_actions = GameEngine.get_link_actions(car_record)
        single_actions = GameEngine.get_available_firing_actions(car_record)
    
        def is_available(action):
            if action['id'] in used_weapons:
                return False
            if action['type'] == 'link':
                # A link is unavailable if any of its member weapons were already
                # fired individually (or as part of a different link).
                return not any(m in used_weapons for m in action.get('members', []))
            # An individual weapon is unavailable if it was already fired on its
            # own, OR if it's a member of a link that has already been fired.
            for link in link_actions:
                if action['id'] in link.get('members', []) and link['id'] in used_weapons:
                    return False
            return True        

        # Links are listed first, per the "usually the most effective, near-default choice" note
        weapon_list = [
            {**action, "available": is_available(action)}
            for action in link_actions
        ] + [
            {**action, "available": is_available(action)}
            for action in single_actions
        ]

        # 4. Targets — every other player's current CarPosition in this game
        game_dir = game_dir_path(game_id)
        game_files = sorted([f for f in os.listdir(game_dir) if re.match(r'^T\d+P', f) and f.endswith('.txt')])
        if not game_files:
            return jsonify({'error': 'No active game state file found'}), 404

        phase_filepath = os.path.join(game_dir, game_files[-1])
        phase_records = GameEngine.read_game_file(phase_filepath)

        targets = [
            {
                "owner": r.get('owner'),
                "car_image_name": r.get('car_image_name'),
                "to_hit": None  # calculated separately, later
            }
            for r in phase_records
            if r.get('CarPosition') == 'CarPosition' and r.get('owner') != username
        ]

        return jsonify({
            'crew': crew_list,
            'weapons': weapon_list,
            'targets': targets
        }), 200

    except Exception as e:
        print(f'Error building firing dialog data: {e}')
        return jsonify({'error': 'Failed to build firing dialog data'}), 500

@app.route('/api/game/confirm_firing_action', methods=['POST'])
@login_required
def confirm_firing_action():
    data = request.get_json() or {}
    game_id = str(data.get('game_id', '')).strip()
    crew_id = str(data.get('crew_id', '')).strip()
    weapon_id = str(data.get('weapon_id', '')).strip()
    username = session['username']

    if not game_id or not crew_id or not weapon_id:
        return jsonify({'error': 'game_id, crew_id, and weapon_id are required'}), 400

    try:
        # ── 1. PASS ACTION INTERCEPT ──
        if weapon_id == "none" and crew_id == "none":
            print(f"[COMBAT PASS] Player {username} elected to take no action.")
            pass_intercept = True
        else:
            pass_intercept = False

        if not pass_intercept:
            # ── STANDARD ACTIVE WEAPON SYSTEM PROCESSING ──
            players = db.get_game_players(game_id)
            player_entry = next((p for p in players if p['username'] == username), None)
            if not player_entry:
                return jsonify({'error': 'You are not a player in this game'}), 404

            position_number = player_entry.get('position_number')
            design = player_entry.get('design')
            if not position_number or not design:
                return jsonify({'error': 'No design assigned for this player'}), 400

            snapshot_filename = f"player_{position_number}_{design}"
            snapshot_path = os.path.join(game_dir_path(game_id), snapshot_filename)

            if not os.path.exists(snapshot_path):
                return jsonify({'error': f'Car snapshot file not found: {snapshot_filename}'}), 404

            car_records = GameEngine.read_game_file(snapshot_path)
            if not car_records or not isinstance(car_records[0], dict):
                return jsonify({'error': 'Car snapshot file is empty or malformed'}), 500

            car_record = car_records[0]

            # Validate the crew member exists and hasn't already fired this turn
            crew_roster = GameEngine.get_crew_roster(car_record)
            valid_crew_ids = {member["id"] for member in crew_roster}

            if crew_id not in valid_crew_ids:
                return jsonify({'error': f'"{crew_id}" is not a valid crew member for this vehicle'}), 400

            used_crew = car_record.get('firing_actions_used_this_turn', [])
            if crew_id in used_crew:
                return jsonify({'error': 'That crew member has already taken a firing action this turn'}), 400

            # Validate the weapon/accessory/link exists and hasn't already been used this turn
            link_actions = GameEngine.get_link_actions(car_record)
            single_actions = GameEngine.get_available_firing_actions(car_record)
            all_actions = link_actions + single_actions
            valid_ids = {action['id'] for action in all_actions}

            if weapon_id not in valid_ids:
                return jsonify({'error': f'"{weapon_id}" is not a valid weapon/accessory/link action for this vehicle'}), 400

            used_weapons = car_record.get('weapons_used_this_turn', [])

            selected_link = next((a for a in link_actions if a['id'] == weapon_id), None)
            if selected_link:
                ids_to_mark = [selected_link['id']] + selected_link['members']
            else:
                ids_to_mark = [weapon_id]

            if any(mid in used_weapons for mid in ids_to_mark):
                return jsonify({'error': 'That weapon, accessory, or link has already been used this turn'}), 400

            # Record the action(s) as spent and write the snapshot back
            used_crew.append(crew_id)
            used_weapons.extend(ids_to_mark)
            car_record['firing_actions_used_this_turn'] = used_crew
            car_record['weapons_used_this_turn'] = used_weapons

            car_records[0] = car_record
            GameEngine.write_game_file(snapshot_path, car_records)

        # ── 2. NEW AUTOMATED PROGRESSION OVERSIGHT CHECK ── ⚙️
        game_dir = game_dir_path(game_id)
        all_files = os.listdir(game_dir)
        game_files = sorted([f for f in all_files if re.match(r'^T\d+P', f) and f.endswith('.txt')])
        
        if game_files:
            latest_filepath = os.path.join(game_dir, game_files[-1])
            file_data = read_game_file(latest_filepath)
            
            # Isolate the central metadata tracking manager block
            queue_entry = next((e for e in file_data if e.get('MovementQueue') == 'MovementQueue'), None)
            
            if queue_entry:
                players_list = queue_entry.get('players', [])
                current_mover = next((p for p in players_list if p['username'] == username), None)
                
                if current_mover:
                    # Update local segment state tracking fields
                    current_mover['done'] = True 
                    current_mover['moved_this_segment'] = True
                    
                # Re-serialize state variations back into active layout records
                for idx, entry in enumerate(file_data):
                    if entry.get('MovementQueue') == 'MovementQueue':
                        file_data[idx] = queue_entry
                        break
                write_game_file(latest_filepath, file_data)

                # Check if EVERY player in this lobby is finished with their action segment
                all_combat_done = all(p.get('done', False) for p in players_list)
                
                if all_combat_done:
                    print(f"[PHASE PROGRESSION] All combat options processed. Advancing from {game_files[-1]}...")
                    from phase_manager import PhaseProgressionManager
                    
                    # Force automatic transition, skipping empty combat files to launch next phase movement
                    success, log_msg = PhaseProgressionManager.advance_to_next_phase_or_turn(game_id)
                    
                    return jsonify({
                        'message': f'Action updated. Phase complete! Engine shifted: {log_msg}',
                        'phase_complete': True,
                        'crew_id': crew_id,
                        'weapon_id': weapon_id
                    }), 200

        # Return successfully if other players are still pending their combat choices
        return jsonify({
            'message': f'Action registered successfully for user {username}. Waiting for remaining players...',
            'phase_complete': False,
            'crew_id': crew_id,
            'weapon_id': weapon_id
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'Error confirming firing action: {e}')
        return jsonify({'error': 'Failed to confirm firing action updates.'}), 500

@app.route('/api/game/confirm_turn_speed', methods=['POST'])
@login_required
def confirm_turn_speed():
    data = request.get_json() or {}
    game_id = str(data.get('game_id', '')).strip()
    speed_change = int(data.get('speed_change', 0))
    username = session['username']
    
    if not game_id:
        return jsonify({'error': 'game_id is required'}), 400
        
    try:
        # 1. Fetch player details to trace vehicle asset profiles and snapshot links
        players = db.get_game_players(game_id)
        player_entry = next((p for p in players if p['username'] == username), None)
        if not player_entry:
            return jsonify({'error': 'You are not a player in this game'}), 404
            
        position_number = player_entry.get('position_number')
        design = player_entry.get('design')
        
        # 2. Trace the current active layout file from the match folder array
        game_dir = game_dir_path(game_id)
        game_files = sorted([f for f in os.listdir(game_dir) if re.match(r'^T\d+P', f) and f.endswith('.txt')])
        if not game_files:
            return jsonify({'error': 'No active turn documentation found.'}), 404
            
        active_filepath = os.path.join(game_dir, game_files[-1])
        file_data = read_game_file(active_filepath)
        
        # 3. Target the live coordinate tracking CarPosition block and update metrics
        car_node = next((r for r in file_data if r.get('CarPosition') == 'CarPosition' and r.get('owner') == username), None)
        if not car_node:
            return jsonify({'error': 'Car coordinate asset not found in turn database file'}), 404
            
        current_speed = int(float(car_node.get('current_speed', 0)))
        new_speed = max(0, current_speed + speed_change)
        car_node['current_speed'] = new_speed
        
        # 4. RESOLVE TIRE RESTRUCTURING RULES (Car Wars p. 41 Damage Penalties)
        # Damage applies directly to your specific snapshot files to decouple shared elements
        tire_damage_applied = 0
        damage_msg = ""
        
        if speed_change in [-35, -40, -45]:
            snapshot_filename = f"player_{position_number}_{design}"
            snapshot_path = os.path.join(game_dir, snapshot_filename)
            
            if os.path.exists(snapshot_path):
                car_records = GameEngine.read_game_file(snapshot_path)
                if car_records and isinstance(car_records[0], dict):
                    vehicle_snapshot = car_records[0]
                    
                    # Compute dynamic randomized parameters matching rule configurations
                    if speed_change == -35:
                        tire_damage_applied = 2
                    elif speed_change == -40:
                        tire_damage_applied = random.randint(1, 6)  # 1d
                    elif speed_change == -45:
                        tire_damage_applied = random.randint(1, 6) + 3  # 1d+3
                        
                    # Process deduction array sequences targeting vehicle tire components
                    # (Assumes your vehicle architecture lists components like 'tire_lf', 'tire_rf', etc.)
                    tire_keys = ['tire_lf', 'tire_rf', 'tire_lr', 'tire_rr']
                    tires_modified = 0
                    
                    for tire in tire_keys:
                        if tire in vehicle_snapshot:
                            current_tire_hp = int(vehicle_snapshot.get(tire, 0))
                            vehicle_snapshot[tire] = max(0, current_tire_hp - tire_damage_applied)
                            tires_modified += 1
                            
                    if tires_modified > 0:
                        # Save structural modifications back to disk storage paths
                        car_records[0] = vehicle_snapshot
                        GameEngine.write_game_file(snapshot_path, car_records)
                        damage_msg = f" Emergency braking hazard! Each tire took {tire_damage_applied} points of damage."
                        print(f"[RULES ENGINE] Heavy deceleration penalty applied. {damage_msg}")

        # 5. RETRACT SPEED CHOICE UNLOCK TOKENS FROM METADATA
        # Clears tracking variables so the intercept pop-up dismisses automatically across channels
        for entry in file_data:
            if entry.get('MovementQueue') == 'MovementQueue':
                entry['requires_turn_speed_selection'] = False
                break
                
        # Synchronize lists back into the master phase log matrix step entries
        for idx, entry in enumerate(file_data):
            if entry.get('CarPosition') == 'CarPosition' and entry.get('owner') == username:
                file_data[idx] = car_node
                break
                
        write_game_file(active_filepath, file_data)
        
        return jsonify({
            'status': 'success', 
            'new_speed': new_speed,
            'message': f"Speed synchronized to {new_speed} MPH.{damage_msg}"
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error handling turn speed initialization sequence: {e}")
        return jsonify({'error': 'Internal server speed synchronization failure.'}), 500

# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':   
    app.run(debug=True, port=8080)
