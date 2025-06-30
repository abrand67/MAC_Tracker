import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

def lookup_mac(mac_address):
    # Normalize input (lowercase, colon format)
    mac = mac_address.lower().replace("-", ":").replace(".", ":")
    if len(mac.replace(":", "")) == 12:
        mac = ":".join([mac[i:i+2] for i in range(0, 12, 2)])

    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT device, interface, first_seen, last_seen
        FROM mac_addresses
        WHERE mac = %s
    """, (mac,))

    result = cursor.fetchone()

    if result:
        device, interface, first_seen, last_seen = result
        print(f"MAC Address: {mac}")
        print(f"Device     : {device}")
        print(f"Interface  : {interface}")
        print(f"First Seen : {first_seen}")
        print(f"Last Seen  : {last_seen}")
    else:
        print(f"MAC address {mac} not found.")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python mac_lookup.py <MAC_ADDRESS>")
        print("Example: python mac_lookup.py aa:bb:cc:dd:ee:ff")
    else:
        lookup_mac(sys.argv[1])
