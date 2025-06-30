# MAC_Tracker
Track location of MAC addresses.

Scheduling:
The main script can be run from crontab as follows:
0 * * * * /usr/bin/python3 /path/to/mac_tracker.py >> /var/log/mac_tracker.log 2>&1
