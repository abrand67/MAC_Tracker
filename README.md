# MAC_Tracker
Track location of MAC addresses on a network.  This script uses SNMP to discover MAC addresses from inventory in NetBox and stores the MAC location information in a PostgreSQL database.

Scheduling:
The main script can be run from crontab as follows:<br>
`0 * * * * /usr/bin/python3 /path/to/mac_tracker.py >> /var/log/mac_tracker.log 2>&1`

The script also logs to `mac_tracker.log` and the following is an example of the log file:<br>
```
2025-06-30 14:00:01,010 - INFO - === MAC Tracker Run Started ===
2025-06-30 14:00:01,112 - INFO - Scanning switch1 (192.168.1.10)
2025-06-30 14:00:01,189 - INFO - [switch1] New MAC aa:bb:cc:dd:ee:ff on Gi1/0/1
2025-06-30 14:00:01,223 - INFO - [switch1] MAC aa:bb:cc:dd:ee:ff seen again on Gi1/0/1
2025-06-30 14:00:01,256 - INFO - [switch1] MAC aa:bb:cc:dd:ee:ff moved from switch1/Gi1/0/1 to switch1/Gi1/0/3
2025-06-30 14:00:01,300 - INFO - === MAC Tracker Run Completed ===
```


The support script, `mac_lookup.py`, will let your query the database for a MAC.  Example:<br>
```
python3 mac_lookup.py aa:bb:cc:dd:ee:ff

MAC Address: aa:bb:cc:dd:ee:ff
Device     : switch1
Interface  : Gi1/0/3
First Seen : 2025-06-28 17:02:45
Last Seen  : 2025-06-30 12:01:00
```
