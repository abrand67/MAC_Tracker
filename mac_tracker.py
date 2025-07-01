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
import threading
import pynetbox
from queue import Queue
from datetime import datetime
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
from pysnmp.hlapi import *
from db_backend import MACStorage

load_dotenv()

# Configuration
NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
THREAD_COUNT = int(os.getenv("THREAD_COUNT", 10))

# SNMP Version and Credentials
SNMP_VERSION = os.getenv("SNMP_VERSION", "v2c").lower()
SNMP_COMMUNITY = os.getenv("SNMP_COMMUNITY", "public")
SNMP_V3_USER = os.getenv("SNMP_V3_USER")
SNMP_V3_AUTH_KEY = os.getenv("SNMP_V3_AUTH_KEY")
SNMP_V3_AUTH_PROTO = os.getenv("SNMP_V3_AUTH_PROTO", "SHA").upper()
SNMP_V3_PRIV_KEY = os.getenv("SNMP_V3_PRIV_KEY")
SNMP_V3_PRIV_PROTO = os.getenv("SNMP_V3_PRIV_PROTO", "AES").upper()

# Logging setup
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mac_tracker")
logger.setLevel(logging.INFO)

file_handler = RotatingFileHandler("mac_tracker.log", maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# SNMP OIDs
BRIDGE_MIB_PORT_OID = '1.3.6.1.2.1.17.4.3.1.2'
PORT_MAP_OID = '1.3.6.1.2.1.17.1.4.1.2'
IFINDEX_TO_NAME_OID = '1.3.6.1.2.1.31.1.1.1.1'

# NetBox API
nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)

def get_snmp_auth():
    if SNMP_VERSION == "v2c":
        return CommunityData(SNMP_COMMUNITY, mpModel=0)
    elif SNMP_VERSION == "v3":
        auth_proto_map = {
            "SHA": usmHMACSHAAuthProtocol,
            "MD5": usmHMACMD5AuthProtocol
        }
        priv_proto_map = {
            "AES": usmAesCfb128Protocol,
            "DES": usmDESPrivProtocol
        }
        return UsmUserData(
            SNMP_V3_USER,
            SNMP_V3_AUTH_KEY,
            SNMP_V3_PRIV_KEY,
            authProtocol=auth_proto_map.get(SNMP_V3_AUTH_PROTO, usmHMACSHAAuthProtocol),
            privProtocol=priv_proto_map.get(SNMP_V3_PRIV_PROTO, usmAesCfb128Protocol)
        )
    else:
        raise ValueError("Unsupported SNMP_VERSION. Use 'v2c' or 'v3'.")

def snmp_walk(ip, oid):
    auth = get_snmp_auth()
    try:
        for (errInd, errStat, errIdx, varBinds) in nextCmd(
            SnmpEngine(),
            auth,
            UdpTransportTarget((ip, 161), timeout=2, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False
        ):
            if errInd:
                logger.warning(f"[{ip}] SNMP error: {errInd}")
                break
            elif errStat:
                logger.warning(f"[{ip}] SNMP error: {errStat.prettyPrint()} at {errIdx}")
                break
            else:
                for varBind in varBinds:
                    yield varBind
    except Exception as e:
        logger.error(f"[{ip}] SNMP walk exception: {e}")

def get_mac_table(ip):
    mac_table, port_map, ifindex_map = {}, {}, {}

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

def worker(queue, store: MACStorage):
    while not queue.empty():
        device, ip = queue.get()
        try:
            logger.info(f"[{device}] Starting scan of {ip}")
            mac_table = get_mac_table(ip)
            for mac, interface in mac_table.items():
                store.upsert_mac(mac, device, interface)
            logger.info(f"[{device}] Completed scan of {ip}")
        except Exception as e:
            logger.exception(f"[{device}] Error during processing")
        finally:
            queue.task_done()

def main():
    logger.info("=== MAC Tracker Run Started ===")
    store = MACStorage()
    try:
        q = Queue()
        devices = nb.dcim.devices.all()
        for dev in devices:
            if dev.primary_ip4:
                ip = dev.primary_ip4.address.split("/")[0]
                q.put((dev.name, ip))

        threads = []
        for _ in range(min(THREAD_COUNT, q.qsize())):
            t = threading.Thread(target=worker, args=(q, store))
            t.start()
            threads.append(t)

        q.join()

        for t in threads:
            t.join()

        store.commit()
        logger.info("=== MAC Tracker Run Completed ===")
    except Exception as e:
        logger.exception("Fatal error in main")
    finally:
        store.close()

if __name__ == "__main__":
    main()
