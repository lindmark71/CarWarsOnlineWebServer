import sqlite3
import os

# ── CONFIGURATION ─────────────────────────────────────────────────────
# Change this string to match your application's actual database filename.
# Common defaults for local prototyping are 'game.db', 'games.db', or 'app.db'.
DB_FILENAME = 'carwars.db' 

def inspect_database():
    if not os.path.exists(DB_FILENAME):
        print(f"❌ CRITICAL ERROR: Database file '{DB_FILENAME}' not found in this directory!")
        print("Please check your file paths or change the DB_FILENAME variable at the top of this script.")
        return

    print("=" * 70)
    print(f"🔍 CORES WARS ENGINE: DATABASE INSPECTION FOR FILE [{DB_FILENAME}]")
    print("=" * 70)

    try:
        # Establish cursor link connection
        conn = sqlite3.connect(DB_FILENAME)
        conn.row_factory = sqlite3.Row  # Allows accessing fields by dictionary keys
        cursor = conn.cursor()

        # 1. Fetch all user-defined tables in the SQLite database
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row['name'] for row in cursor.fetchall()]

        if not tables:
            print("⚠️ Notice: The database file exists, but it contains zero tables.")
            return

        for table_name in tables:
            print(f"\n📋 TABLE STRUCTURE: [{table_name}]")
            print("-" * 70)

            # 2. Inspect Column schema definition properties (Name, Type, Nullable, Default, PK)
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            
            print(f"{'Col ID':<8}{'Column Name':<25}{'Data Type':<15}{'NotNull':<10}{'PK':<5}")
            print("." * 70)
            for col in columns:
                print(f"{col['cid']:<8}{col['name']:<25}{col['type']:<15}{col['notnull']:<10}{col['pk']:<5}")

            # 3. Fetch and dump raw table data rows
            print("\n📦 ROW CONTENTS:")
            print("." * 70)
            cursor.execute(f"SELECT * FROM {table_name};")
            rows = cursor.fetchall()

            if not rows:
                print("   (Table is currently empty)")
            else:
                for idx, row in enumerate(rows):
                    # Convert the row structure directly to a scannable dictionary output
                    row_dict = dict(row)
                    print(f"   Row #{idx + 1}: {row_dict}")
            
            print("=" * 70)

        conn.close()

    except sqlite3.Error as e:
        print(f"❌ DATABASE PROCESSING CRASH: {e}")

if __name__ == "__main__":
    inspect_database()