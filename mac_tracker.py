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
import pynetbox
from datetime import datetime
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
from pysnmp.hlapi import *
from db_backend import MACStorage

# Load environment
load_dotenv()

# Configuration
NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
SNMP_COMMUNITY = os.getenv("SNMP_COMMUNITY", "public")

# Logging setup
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mac_tracker")
logger.setLevel(logging.INFO)

# File log
log_file = "mac_tracker.log"
file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Console log
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

def process_device(store: MACStorage, device_name, ip):
    logger.info(f"Scanning {device_name} ({ip})")
    try:
        mac_table = get_mac_table(ip)
        for mac, interface in mac_table.items():
            store.upsert_mac(mac, device_name, interface)
    except Exception as e:
        logger.exception(f"[{device_name}] Error during processing")

def main():
    logger.info("=== MAC Tracker Run Started ===")
    store = MACStorage()
    try:
        devices = nb.dcim.devices.all()
        for device in devices:
            if device.primary_ip4:
                ip = device.primary_ip4.address.split("/")[0]
                process_device(store, device.name, ip)
        store.commit()
        logger.info("=== MAC Tracker Run Completed ===")
    except Exception as e:
        logger.exception("Fatal error in main")
    finally:
        store.close()

if __name__ == "__main__":
    main()
