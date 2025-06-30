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
import logging
import psycopg2
import pynetbox
from dotenv import load_dotenv
from datetime import datetime
from pysnmp.hlapi import *
from logging.handlers import RotatingFileHandler

# Load environment
load_dotenv()

# Configuration
NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
SNMP_COMMUNITY = os.getenv("SNMP_COMMUNITY")

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

# Setup logging
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mac_tracker")
logger.setLevel(logging.INFO)

# File handler (rotate logs)
log_file = "/var/log/mac_tracker.log"
file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# SNMP OIDs
BRIDGE_MIB_PORT_OID = '1.3.6.1.2.1.17.4.3.1.2'
PORT_MAP_OID = '1.3.6.1.2.1.17.1.4.1.2'
IFINDEX_TO_NAME_OID = '1.3.6.1.2.1.31.1.1.1.1'

# Connect to NetBox
nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)

def snmp_walk(ip, oid):
    try:
        for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
            SnmpEngine(),
            CommunityData(SNMP_COMMUNITY, mpModel=0),
            UdpTransportTarget((ip, 161), timeout=2, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False
        ):
            if errorIndication:
                logger.warning(f"[{ip}] SNMP error: {errorIndication}")
                break
            elif errorStatus:
                logger.warning(f"[{ip}] SNMP error: {errorStatus.prettyPrint()} at {errorIndex}")
                break
            else:
                for varBind in varBinds:
                    yield varBind
    except Exception as e:
        logger.error(f"[{ip}] SNMP walk exception: {e}")

def get_mac_table(ip):
    mac_table = {}
    port_map = {}
    ifindex_map = {}

    for oid, val in snmp_walk(ip, PORT_MAP_OID):
        bridge_port = int(oid.prettyPrint().split('.')[-1])
        port_map[bridge_port] = int(val.prettyPrint())

    for oid, val in snmp_walk(ip, IFINDEX_TO_NAME_OID):
        ifindex = int(oid.prettyPrint().split('.')[-1])
        ifindex_map[ifindex] = val.prettyPrint()

    for oid, val in snmp_walk(ip, BRIDGE_MIB_PORT_OID):
        mac_oid = oid.prettyPrint()
        bridge_port = int(val.prettyPrint())
        mac_raw = mac_oid.split('.')[-6:]
        mac = ':'.join(f"{int(b):02x}" for b in mac_raw)

        if bridge_port in port_map:
            ifindex = port_map[bridge_port]
            interface = ifindex_map.get(ifindex, f"ifIndex-{ifindex}")
            mac_table[mac] = interface

    return mac_table

def ensure_tables(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mac_addresses (
        id SERIAL PRIMARY KEY,
        mac TEXT UNIQUE,
        device TEXT,
        interface TEXT,
        first_seen TIMESTAMP,
        last_seen TIMESTAMP
    );
    """)
    cursor.execute("""
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

def upsert_mac(cursor, mac, device, interface, now):
    cursor.execute("SELECT device, interface, first_seen FROM mac_addresses WHERE mac = %s", (mac,))
    row = cursor.fetchone()

    if row:
        old_device, old_if, first_seen = row
        if old_device == device and old_if == interface:
            cursor.execute("""
                UPDATE mac_addresses SET last_seen = %s WHERE mac = %s
            """, (now, mac))
            logger.info(f"[{device}] MAC {mac} seen again on {interface}")
        else:
            # MAC moved
            cursor.execute("""
                INSERT INTO mac_movements (mac, from_device, from_if, to_device, to_if, moved_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (mac, old_device, old_if, device, interface, now))
            cursor.execute("""
                UPDATE mac_addresses
                SET device = %s, interface = %s, last_seen = %s
                WHERE mac = %s
            """, (device, interface, now, mac))
            logger.info(f"[{device}] MAC {mac} moved from {old_device}/{old_if} to {device}/{interface}")
    else:
        cursor.execute("""
            INSERT INTO mac_addresses (mac, device, interface, first_seen, last_seen)
            VALUES (%s, %s, %s, %s, %s)
        """, (mac, device, interface, now, now))
        logger.info(f"[{device}] New MAC {mac} on {interface}")

def process_device(cursor, device_name, ip):
    logger.info(f"Scanning {device_name} ({ip})")
    try:
        mac_table = get_mac_table(ip)
        now = datetime.utcnow()
        for mac, interface in mac_table.items():
            upsert_mac(cursor, mac, device_name, interface, now)
    except Exception as e:
        logger.exception(f"[{device_name}] Error during processing")

def main():
    logger.info("=== MAC Tracker Run Started ===")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        ensure_tables(cursor)

        devices = nb.dcim.devices.all()
        for device in devices:
            if device.primary_ip4:
                ip = device.primary_ip4.address.split("/")[0]
                process_device(cursor, device.name, ip)

        conn.commit()
        cursor.close()
        conn.close()
        logger.info("=== MAC Tracker Run Completed ===")
    except Exception as e:
        logger.exception("Fatal error in main")

if __name__ == "__main__":
    main()
