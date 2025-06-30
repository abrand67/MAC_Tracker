"""
Copyright 2025 Allan Brand

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os
import psycopg2
from dotenv import load_dotenv
from tabulate import tabulate
import argparse

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

def normalize_mac(mac_input):
    mac = mac_input.lower().replace("-", "").replace(":", "").replace(".", "")
    return mac

def search_mac(cursor, mac_query, show_history=False):
    mac_fragment = normalize_mac(mac_query)

    # Match MACs with or without colons
    cursor.execute("""
        SELECT mac, device, interface, first_seen, last_seen
        FROM mac_addresses
        WHERE REPLACE(REPLACE(REPLACE(mac, ':', ''), '-', ''), '.', '') ILIKE %s
        ORDER BY last_seen DESC
    """, (f"%{mac_fragment}%",))
    
    results = cursor.fetchall()

    if not results:
        print("No MAC address found.")
        return

    headers = ["MAC", "Device", "Interface", "First Seen", "Last Seen"]
    print("\nCurrent MAC Info:\n")
    print(tabulate(results, headers=headers))

    if show_history:
        print("\nMovement History:\n")
        for row in results:
            mac = row[0]
            cursor.execute("""
                SELECT from_device, from_if, to_device, to_if, moved_at
                FROM mac_movements
                WHERE mac = %s
                ORDER BY moved_at DESC
            """, (mac,))
            history = cursor.fetchall()
            if history:
                print(f"History for {mac}:\n")
                print(tabulate(history, headers=["From Device", "From IF", "To Device", "To IF", "Moved At"]))
                print()

def main():
    parser = argparse.ArgumentParser(description="Lookup MAC address info from PostgreSQL.")
    parser.add_argument("mac", help="Full or partial MAC address to search")
    parser.add_argument("--history", action="store_true", help="Show movement history for matching MACs")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    search_mac(cursor, args.mac, args.history)

    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()
