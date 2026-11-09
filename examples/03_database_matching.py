#!/usr/bin/env python3
"""
Example 3: SQLite Database Storage & 1:N Biometric Identification
Demonstrates storing biometric templates in an SQL database and performing
1:N identification (finding who the finger belongs to among all enrolled users).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3
from dp4500 import UareU4500, FingerprintTemplate
from dp4500.backends.mock import MockBackend

DB_FILE = "users_biometrics.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            finger_name TEXT,
            template_blob BLOB NOT NULL,
            created_at REAL
        )
    """)
    conn.commit()
    return conn

def enroll_user_to_db(conn, reader, username, finger_name="right_index"):
    print(f"\nEnrolling '{username}' ({finger_name})...")
    tpl = reader.enroll(stages=2, username=username, finger_name=finger_name)

    # Store serialized template bytes in database BLOB
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (username, finger_name, template_blob, created_at)
        VALUES (?, ?, ?, ?)
    """, (username, finger_name, tpl.to_bytes(), tpl.created_at))
    conn.commit()
    print(f"Stored template for '{username}' in SQLite database.")

def identify_user_from_db(conn, reader):
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, template_blob FROM users")
    rows = cursor.fetchall()

    if not rows:
        print("No enrolled users in database.")
        return

    # Load all candidate templates
    candidate_templates = []
    user_map = {}
    for idx, (user_id, username, blob) in enumerate(rows):
        tpl = FingerprintTemplate.from_bytes(blob)
        candidate_templates.append(tpl)
        user_map[idx] = username

    print(f"\nIdentifying live finger against {len(candidate_templates)} enrolled user(s)...")
    res = reader.identify(candidate_templates)

    if res.matched and res.index is not None:
        identified_user = user_map[res.index]
        print(f"[✓] IDENTIFIED: Match found for '{identified_user}'! (Score: {res.score:.2f})")
    else:
        print("[✗] UNRECOGNIZED: No matching fingerprint in database.")

def main():
    use_mock = "--mock" in sys.argv or True  # Default to mock for illustration
    backend = MockBackend() if use_mock else None

    conn = init_db()

    with UareU4500(backend=backend) as reader:
        # Simulate different fingers in mock mode
        if hasattr(reader._handle, "simulated_finger_seed"):
            reader._handle.simulated_finger_seed = 101
            enroll_user_to_db(conn, reader, "alice")

            reader._handle.simulated_finger_seed = 202
            enroll_user_to_db(conn, reader, "bob")

            reader._handle.simulated_finger_seed = 303
            enroll_user_to_db(conn, reader, "charlie")

            # Now pretend Bob puts his finger on the scanner
            print("\n>>> Bob steps up and places his finger on the scanner...")
            reader._handle.simulated_finger_seed = 202
            identify_user_from_db(conn, reader)
        else:
            identify_user_from_db(conn, reader)

    conn.close()

if __name__ == "__main__":
    main()
