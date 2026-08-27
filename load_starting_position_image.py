"""
load_starting_position_images.py

Admin script to load starting position BMP images into the database.

Usage:
    python load_starting_position_images.py

Place your BMP files in the same folder as this script, or set
IMAGE_FOLDER below to wherever they live.

Expected filenames (name is derived by stripping the extension):
    blue.bmp    → stored as name='blue'
    red.bmp     → stored as name='red'
    green.bmp   → stored as name='green'
    yellow.bmp  → stored as name='yellow'
    white.bmp   → stored as name='white'
    orange.bmp  → stored as name='orange'
    purple.bmp  → stored as name='purple'
    pink.bmp    → stored as name='pink'

You can also pass a custom folder as a command-line argument:
    python load_starting_position_images.py C:\\path\\to\\images
"""

import os
import sys
import base64
import sqlite3
from datetime import datetime
from PIL import Image
from io import BytesIO

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DB_PATH      = os.path.join(BASE_DIR, 'carwars.db')

# Default: look for BMP files in the same folder as this script.
# Override by passing a folder path as a command-line argument.
IMAGE_FOLDER = sys.argv[1] if len(sys.argv) > 1 else BASE_DIR

# Expected image dimensions — same as car images
EXPECTED_WIDTH  = 21
EXPECTED_HEIGHT = 41

# Accepted file extensions
ACCEPTED_EXTENSIONS = {'.bmp', '.png', '.gif'}

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_image_as_base64(filepath: str) -> str:
    """Read an image file and return its base64-encoded string."""
    with open(filepath, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

def validate_image(filepath: str) -> tuple:
    """
    Open the image with Pillow and check its dimensions.
    Returns (True, width, height) if valid, (False, w, h) if wrong size.
    """
    try:
        img = Image.open(filepath)
        w, h = img.size
        return (w == EXPECTED_WIDTH and h == EXPECTED_HEIGHT), w, h
    except Exception as e:
        print(f'  ERROR: Could not open image: {e}')
        return False, 0, 0

def register_in_db(name: str, base64_data: str) -> bool:
    """Insert or replace a starting position image in the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''
            INSERT OR REPLACE INTO starting_position_images
                (name, base64_data, uploaded_at)
            VALUES (?, ?, ?)
        ''', (name, base64_data, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f'  ERROR: Database write failed: {e}')
        return False

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f'Car Wars Online — Starting Position Image Loader')
    print(f'{'─' * 50}')
    print(f'Database : {DB_PATH}')
    print(f'Image folder: {IMAGE_FOLDER}')
    print()

    if not os.path.exists(DB_PATH):
        print('ERROR: Database not found. Run create_database.py first.')
        sys.exit(1)

    if not os.path.exists(IMAGE_FOLDER):
        print(f'ERROR: Image folder not found: {IMAGE_FOLDER}')
        sys.exit(1)

    # Find all image files in the folder
    candidates = [
        f for f in os.listdir(IMAGE_FOLDER)
        if os.path.splitext(f)[1].lower() in ACCEPTED_EXTENSIONS
    ]

    if not candidates:
        print(f'No image files found in {IMAGE_FOLDER}')
        print(f'Expected extensions: {", ".join(ACCEPTED_EXTENSIONS)}')
        sys.exit(0)

    print(f'Found {len(candidates)} image file(s):\n')

    loaded  = 0
    skipped = 0
    errors  = 0

    for filename in sorted(candidates):
        filepath = os.path.join(IMAGE_FOLDER, filename)
        name     = os.path.splitext(filename)[0].lower()   # 'blue.bmp' → 'blue'

        print(f'  {filename} → name="{name}"')

        # Validate dimensions
        valid, w, h = validate_image(filepath)
        if not valid:
            if w == 0 and h == 0:
                errors += 1
                continue
            print(f'  WARNING: Expected {EXPECTED_WIDTH}x{EXPECTED_HEIGHT} '
                  f'pixels, got {w}x{h}. Skipping.')
            skipped += 1
            continue

        # Convert to base64
        try:
            base64_data = load_image_as_base64(filepath)
        except Exception as e:
            print(f'  ERROR: Could not read file: {e}')
            errors += 1
            continue

        # Write to database
        if register_in_db(name, base64_data):
            print(f'  OK — loaded ({w}x{h} pixels, '
                  f'{len(base64_data):,} base64 chars)')
            loaded += 1
        else:
            errors += 1

    print()
    print(f'{'─' * 50}')
    print(f'Done. Loaded: {loaded}  Skipped: {skipped}  Errors: {errors}')

    # Show what's now in the database
    print()
    print('Starting position images now in database:')
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        'SELECT name, uploaded_at FROM starting_position_images ORDER BY name'
    ).fetchall()
    conn.close()
    if rows:
        for row in rows:
            print(f'  {row[0]:<20} uploaded: {row[1][:16]}')
    else:
        print('  (none)')

if __name__ == '__main__':
    main()
