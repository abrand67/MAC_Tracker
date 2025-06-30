# MAC_Tracker
Track location of MAC addresses.

Scheduling:
The main script can be run from crontab as follows:<br>
`0 * * * * /usr/bin/python3 /path/to/mac_tracker.py >> /var/log/mac_tracker.log 2>&1`

Example of the support script:<br>
`python3 mac_lookup.py aa:bb:cc:dd:ee:ff

MAC Address: aa:bb:cc:dd:ee:ff
Device     : switch1
Interface  : Gi1/0/3
First Seen : 2025-06-28 17:02:45
Last Seen  : 2025-06-30 12:01:00`
