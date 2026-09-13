import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_FILE  = os.path.join(BASE_DIR, 'carwars.db')

def run_migration():
    if not os.path.exists(DATABASE_FILE):
        print(f"Could not locate database at {DATABASE_FILE}. Double-check your database file name context path.")
        return

    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    print("Staging database table modification metrics...")

    # 1. Inject the Minimum Speed tracking boundary column
    try:
        cursor.execute("ALTER TABLE games ADD COLUMN min_initial_speed INTEGER DEFAULT 0;")
        conn.commit()
        print("✔ Column 'min_initial_speed' successfully added.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("⚠ Column 'min_initial_speed' already exists. Skipping.")
        else:
            print(f"❌ Structural alteration error on min_initial_speed: {e}")

    # 2. Inject the Maximum Speed constraint tracking column (matching your existing 'initial_speed' naming rule)
    try:
        cursor.execute("ALTER TABLE games ADD COLUMN initial_speed INTEGER DEFAULT 60;")
        conn.commit()
        print("✔ Column 'initial_speed' successfully added.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("⚠ Column 'initial_speed' already exists. Skipping.")
        else:
            print(f"❌ Structural alteration error on initial_speed: {e}")

    print("\nMigration cycle complete. Closing connection sheets.")
    conn.close()

if __name__ == '__main__':
    run_migration()
