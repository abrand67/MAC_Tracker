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
from dotenv import load_dotenv
from tabulate import tabulate
import argparse
from datetime import datetime
from db_backend import MACStorage

load_dotenv()

def normalize_mac(mac_input):
    return mac_input.lower().replace("-", "").replace(":", "").replace(".", "")

def format_mac(mac):
    mac = normalize_mac(mac)
    return ":".join(mac[i:i+2] for i in range(0, len(mac), 2))

def search_mac_partial(store: MACStorage, mac_fragment: str, show_history: bool):
    db_backend = os.getenv("DB_BACKEND", "postgres").lower()
    mac_fragment = normalize_mac(mac_fragment)

    if db_backend == "postgres":
        import psycopg2
        conn = store.conn
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mac, device, interface, first_seen, last_seen
            FROM mac_addresses
            WHERE REPLACE(REPLACE(REPLACE(mac, ':', ''), '-', ''), '.', '') ILIKE %s
            ORDER BY last_seen DESC
        """, (f"%{mac_fragment}%",))
        rows = cursor.fetchall()

        if not rows:
            print("No MACs found.")
            return

        print("\nCurrent MAC Info:")
        print(tabulate(rows, headers=["MAC", "Device", "Interface", "First Seen", "Last Seen"]))

        if show_history:
            for mac, *_ in rows:
                cursor.execute("""
                    SELECT from_device, from_if, to_device, to_if, moved_at
                    FROM mac_movements
                    WHERE mac = %s
                    ORDER BY moved_at DESC
                """, (mac,))
                history = cursor.fetchall()
                if history:
                    print(f"\nHistory for {mac}:")
                    print(tabulate(history, headers=["From Device", "From IF", "To Device", "To IF", "Moved At"]))

    elif db_backend == "mongo":
        macs = store.mac_coll.find({
            "$expr": {
                "$regexMatch": {
                    "input": {"$replaceAll": {"input": "$mac", "find": ":", "replacement": ""}},
                    "regex": mac_fragment,
                    "options": "i"
                }
            }
        }).sort("last_seen", -1)

        mac_list = list(macs)

        if not mac_list:
            print("No MACs found.")
            return

        print("\nCurrent MAC Info:")
        table = [
            [d['mac'], d['device'], d['interface'], d['first_seen'], d['last_seen']]
            for d in mac_list
        ]
        print(tabulate(table, headers=["MAC", "Device", "Interface", "First Seen", "Last Seen"]))

        if show_history:
            for d in mac_list:
                mac = d['mac']
                movements = store.movements.find({"mac": mac}).sort("moved_at", -1)
                history = [
                    [m['from_device'], m['from_if'], m['to_device'], m['to_if'], m['moved_at']]
                    for m in movements
                ]
                if history:
                    print(f"\nHistory for {mac}:")
                    print(tabulate(history, headers=["From Device", "From IF", "To Device", "To IF", "Moved At"]))

    else:
        print("Unsupported DB_BACKEND")

def main():
    parser = argparse.ArgumentParser(description="MAC address lookup (PostgreSQL or MongoDB).")
    parser.add_argument("mac", help="Full or partial MAC address")
    parser.add_argument("--history", action="store_true", help="Include movement history")
    args = parser.parse_args()

    store = MACStorage()
    try:
        search_mac_partial(store, args.mac, args.history)
    finally:
        store.close()

if __name__ == "__main__":
    main()

