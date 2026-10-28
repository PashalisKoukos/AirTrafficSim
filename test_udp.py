# ---------------------------------------------------------
# test_udp.py
# Manual test helper: sends one UDP position packet to the server.
#
# The packet is intentionally NOT signed, so the server should
# reject it with an HMAC failure. This verifies that message
# authentication is enforced.
# ---------------------------------------------------------

import socket
import json

# Function that reads aircraft data from the SQLite database.
from dataBase import get_aircraft


# IP address and port the UDP server listens on.
SERVER_IP = "127.0.0.1"
SERVER_PORT = 5000

# Read the current data of the second aircraft. Its position is
# used to place the first aircraft at exactly the same point.
aircraft_b = get_aircraft("AC002")

# Make sure the aircraft exists in the database.
if aircraft_b is None:
    print("Error: AC002 was not found in the database.")

else:
    # Build a position message for AC001. The coordinates equal
    # those of AC002, so the distance between them would be zero.
    message = {
        "type": "POSITION",
        "aircraft_id": "AC001",
        "seq": 1,
        "x": aircraft_b["x"],
        "y": aircraft_b["y"],
        "speed": 2.0,
        "heading": 90.0
    }

    # UDP carries raw bytes, so serialize the dict to JSON
    # and encode it as UTF-8.
    data = json.dumps(message).encode("utf-8")

    # Create a UDP socket and send the datagram to the server.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(data, (SERVER_IP, SERVER_PORT))

    # Inform the user that the packet was sent.
    print("Sent test position for AC001:", message)