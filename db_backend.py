

import os
import psycopg2
from pymongo import MongoClient
from datetime import datetime

DB_BACKEND = os.getenv("DB_BACKEND", "postgres")

if DB_BACKEND == "postgres":
    DB_CONFIG = {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
        "dbname": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }
elif DB_BACKEND == "mongo":
    MONGO_URI = os.getenv("MONGO_URI")
    MONGO_DB = os.getenv("MONGO_DB")
else:
    raise ValueError("Invalid DB_BACKEND. Use 'postgres' or 'mongo'.")

class MACStorage:
    def __init__(self):
        if DB_BACKEND == "postgres":
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cursor = self.conn.cursor()
            self._ensure_postgres_tables()
        else:
            self.client = MongoClient(MONGO_URI)
            self.db = self.client[MONGO_DB]
            self.mac_coll = self.db["mac_addresses"]
            self.movements = self.db["mac_movements"]

    def _ensure_postgres_tables(self):
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS mac_addresses (
            id SERIAL PRIMARY KEY,
            mac TEXT UNIQUE,
            device TEXT,
            interface TEXT,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP
        );
        """)
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS mac_movements (
            id SERIAL PRIMARY KEY,
            mac TEXT,
            from_device TEXT,
            from_if TEXT,
            to_device TEXT,
            to_if TEXT,
            moved_at TIMESTAMP
        );
        """)

    def upsert_mac(self, mac, device, interface):
        now = datetime.utcnow()

        if DB_BACKEND == "postgres":
            self.cursor.execute("SELECT device, interface FROM mac_addresses WHERE mac = %s", (mac,))
            row = self.cursor.fetchone()
            if row:
                old_device, old_if = row
                if old_device == device and old_if == interface:
                    self.cursor.execute("UPDATE mac_addresses SET last_seen = %s WHERE mac = %s", (now, mac))
                else:
                    self.cursor.execute("""
                        INSERT INTO mac_movements (mac, from_device, from_if, to_device, to_if, moved_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (mac, old_device, old_if, device, interface, now))
                    self.cursor.execute("""
                        UPDATE mac_addresses SET device = %s, interface = %s, last_seen = %s WHERE mac = %s
                    """, (device, interface, now, mac))
            else:
                self.cursor.execute("""
                    INSERT INTO mac_addresses (mac, device, interface, first_seen, last_seen)
                    VALUES (%s, %s, %s, %s, %s)
                """, (mac, device, interface, now, now))
        else:
            existing = self.mac_coll.find_one({"mac": mac})
            if existing:
                if existing["device"] == device and existing["interface"] == interface:
                    self.mac_coll.update_one({"mac": mac}, {"$set": {"last_seen": now}})
                else:
                    self.movements.insert_one({
                        "mac": mac,
                        "from_device": existing["device"],
                        "from_if": existing["interface"],
                        "to_device": device,
                        "to_if": interface,
                        "moved_at": now
                    })
                    self.mac_coll.update_one({"mac": mac}, {"$set": {
                        "device": device,
                        "interface": interface,
                        "last_seen": now
                    }})
            else:
                self.mac_coll.insert_one({
                    "mac": mac,
                    "device": device,
                    "interface": interface,
                    "first_seen": now,
                    "last_seen": now
                })

    def commit(self):
        if DB_BACKEND == "postgres":
            self.conn.commit()

    def close(self):
        if DB_BACKEND == "postgres":
            self.cursor.close()
            self.conn.close()
        else:
            self.client.close()
