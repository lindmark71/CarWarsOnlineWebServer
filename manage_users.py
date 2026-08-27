import bcrypt
import json
import os
import re

CREDENTIALS_FILE = './credentials.json'

# ── Twilio Setup (for SMS) ────────────────────────────────────────────────────
#
# STEP 1: Create a free Twilio account at https://www.twilio.com/try-twilio
#         You will receive $15 in free credits — enough for ~1,900 SMS messages.
#
# STEP 2: From the Twilio Console (https://console.twilio.com) note down:
#           - Account SID  (looks like: ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx)
#           - Auth Token   (looks like: your_auth_token)
#           - Phone Number (a Twilio number you'll be assigned, e.g. +12015551234)
#
# STEP 3: Install the Twilio Python library:
#           pip install twilio
#
# STEP 4: Fill in the three values below.
#         For production, use environment variables instead of hardcoding:
#           import os
#           TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
#
# ─────────────────────────────────────────────────────────────────────────────

TWILIO_ACCOUNT_SID = 'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'   # ← replace
TWILIO_AUTH_TOKEN  = 'your_auth_token'                      # ← replace
TWILIO_FROM_NUMBER = '+12015551234'                         # ← replace with your Twilio number

def load_credentials():
    if not os.path.exists(CREDENTIALS_FILE):
        return {}
    with open(CREDENTIALS_FILE, 'r') as f:
        return json.load(f)

def save_credentials(credentials):
    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump(credentials, f, indent=2)

def normalize_phone(phone: str) -> str:
    """
    Normalize a phone number to E.164 format (+12155551234).
    Strips spaces, dashes, parentheses and dots.
    Returns empty string if the result doesn't look like a valid E.164 number.
    """
    if not phone:
        return ''
    # Strip all non-digit and non-plus characters
    cleaned = re.sub(r'[^\d+]', '', phone.strip())
    # Must start with + and have 7-15 digits after it
    if re.match(r'^\+\d{7,15}$', cleaned):
        return cleaned
    return ''

def add_user(username, password, email, phone=''):
    credentials = load_credentials()
    if username in credentials:
        print(f'User "{username}" already exists. Use update_* functions to make changes.')
        return
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    credentials[username] = {
        'password': hashed.decode('utf-8'),
        'email':    email,
        'phone':    normalize_phone(phone)
    }
    save_credentials(credentials)
    print(f'User "{username}" added successfully.')

def update_password(username, new_password):
    credentials = load_credentials()
    if username not in credentials:
        print(f'User "{username}" not found.')
        return
    hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    credentials[username]['password'] = hashed.decode('utf-8')
    save_credentials(credentials)
    print(f'Password for "{username}" updated.')

def update_email(username, new_email):
    credentials = load_credentials()
    if username not in credentials:
        print(f'User "{username}" not found.')
        return
    credentials[username]['email'] = new_email
    save_credentials(credentials)
    print(f'Email for "{username}" updated to "{new_email}".')

def update_phone(username, new_phone):
    """Update a user's phone number. Pass an empty string to remove it."""
    credentials = load_credentials()
    if username not in credentials:
        print(f'User "{username}" not found.')
        return
    normalized = normalize_phone(new_phone)
    if new_phone and not normalized:
        print(f'Invalid phone number format. Use E.164 format, e.g. +12155551234')
        return
    credentials[username]['phone'] = normalized
    save_credentials(credentials)
    if normalized:
        print(f'Phone for "{username}" updated to "{normalized}".')
    else:
        print(f'Phone for "{username}" removed.')

def delete_user(username):
    credentials = load_credentials()
    if username not in credentials:
        print(f'User "{username}" not found.')
        return
    del credentials[username]
    save_credentials(credentials)
    print(f'User "{username}" deleted.')

def list_users():
    credentials = load_credentials()
    if not credentials:
        print('No users found.')
        return
    print(f'{"Username":<20} {"Email":<30} {"Phone":<16}')
    print('-' * 68)
    for username, data in credentials.items():
        if isinstance(data, dict):
            email = data.get('email', '(none)')
            phone = data.get('phone', '') or '(none)'
        else:
            email = '(old format — no email)'
            phone = '(none)'
        print(f'{username:<20} {email:<30} {phone:<16}')

def send_sms(to_number: str, message: str) -> bool:
    """
    Send an SMS message via Twilio.
    Returns True on success, False on failure.
    Requires the twilio library: pip install twilio
    """
    if not to_number:
        print('No phone number provided — SMS not sent.')
        return False

    if TWILIO_ACCOUNT_SID.startswith('AC' + 'x'):
        print('Twilio credentials not configured. See setup comments at the top of this file.')
        return False

    try:
        from twilio.rest import Client
        client  = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body = message,
            from_= TWILIO_FROM_NUMBER,
            to   = to_number
        )
        print(f'SMS sent to {to_number}. SID: {message.sid}')
        return True
    except ImportError:
        print('Twilio library not installed. Run: pip install twilio')
        return False
    except Exception as e:
        print(f'SMS send failed: {e}')
        return False

# ── Command Line Usage ────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Examples — uncomment the ones you need:

    # add_user('admin',   'secretpassword', 'admin@example.com',   '+12155551234')
    # add_user('player1', 'carwars123',     'player1@example.com', '')
    # update_phone('admin', '+12155559999')
    # update_email('admin', 'newemail@example.com')
    # update_password('player1', 'newpassword')
    # delete_user('player1')
    list_users()
