import sqlite3
import json
import os

# Define database path relative to this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'network_monitor.db')

print(f"Checking database at: {DATABASE}")

if not os.path.exists(DATABASE):
    print("Database file not found!")
    exit(1)

try:
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n--- Devices ---")
    cursor.execute("SELECT ip, group_name, user, status FROM devices")
    devices = cursor.fetchall()
    print(f"Total devices found: {len(devices)}")
    for d in devices:
        print(f"IP: {d['ip']}, Group: {d['group_name']}, User: {d['user']}, Status: {d['status']}")

    print("\n--- Config (Device Groups SSH) ---")
    cursor.execute("SELECT device_groups FROM config")
    row = cursor.fetchone()
    if row:
        try:
            groups = json.loads(row['device_groups'])
            for g in groups:
                print(f"Group: {g['name']}")
                ssh = g.get('sshConfig', {})
                print(f"  SSH Config: User={ssh.get('username')}, Port={ssh.get('port')}, KeyAuth={ssh.get('keyAuth')}")
        except json.JSONDecodeError:
            print("Error decoding device_groups JSON")
    else:
        print("No config found")

    conn.close()
except Exception as e:
    print(f"Error: {e}")
import sqlite3
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'network_monitor.db')

print(f"Checking database at: {DATABASE}")

try:
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n--- Devices ---")
    cursor.execute("SELECT ip, group_name, user FROM devices")
    devices = cursor.fetchall()
    for d in devices:
        print(f"IP: {d['ip']}, Group: {d['group_name']}, User: {d['user']}")

    print("\n--- Config ---")
    cursor.execute("SELECT device_groups FROM config")
    row = cursor.fetchone()
    if row:
        groups = json.loads(row['device_groups'])
        for g in groups:
            print(f"Group: {g['name']}")
            print(f"  SSH Config: {g.get('sshConfig')}")
    else:
        print("No config found")

    conn.close()
except Exception as e:
    print(f"Error: {e}")