# ---------------------------------------------------------
# aircraft.py
# Simulates aircraft movement and UDP communication.
# Every position message is protected with HMAC-SHA-256.
# ---------------------------------------------------------

import json
import math
import socket
import time

# Database helpers: create the database and read the initial
# aircraft data.
from dataBase import (
    create_database,
    insert_initial_aircraft,
    get_aircraft
)

# HMAC helpers for signing outgoing and verifying incoming messages.
from security import create_hmac, verify_hmac


# IP address of the server.
HOST = "127.0.0.1"

# Port to which position updates are sent.
PORT = 5000

# Port on which heading commands are received.
COMMAND_PORT = 5002

# Boundaries of the airspace in which the aircraft move.
MIN_COORDINATE = 0.0
MAX_COORDINATE = 100.0

# Identifiers of the five simulated aircraft.
AIRCRAFT_IDS = ["AC001", "AC002", "AC003", "AC004", "AC005"]


def receive_commands(command_socket, aircraft_list):
    """
    Process commands received from the server.

    The HMAC-SHA-256 signature is verified before any HEADING
    command is applied.
    """

    # Read every message that is currently waiting on the socket.
    while True:
        try:
            # Receive one UDP packet from the server.
            data, address = command_socket.recvfrom(4096)

        except BlockingIOError:
            # No more messages are available right now.
            break

        try:
            # Convert the received bytes into a Python dict.
            command = json.loads(data.decode("utf-8"))

            # Accept only JSON objects.
            if not isinstance(command, dict):
                continue

            # Read the signature sent by the server.
            received_signature = command.get("hmac")

            # Reject commands that carry no signature.
            if not isinstance(received_signature, str):
                print("Rejected: command has no HMAC.")
                continue

            # Work on a copy without the hmac field, because the
            # signature was originally computed without it.
            command_to_verify = command.copy()
            command_to_verify.pop("hmac")

            # Verify that the signature is valid.
            if not verify_hmac(command_to_verify, received_signature):
                print("Rejected: HMAC verification failed.")
                continue

            # From here on only correctly signed commands are handled.
            if command.get("type") != "HEADING":
                continue

            # Read the target aircraft and the requested heading.
            aircraft_id = command.get("aircraft_id")
            heading = command.get("heading")

            # The heading must be a finite number in [0, 360).
            # Booleans are rejected explicitly because bool is a
            # subclass of int in Python.
            if (
                isinstance(heading, bool)
                or not isinstance(heading, (int, float))
                or not math.isfinite(heading)
                or not 0 <= heading < 360
            ):
                print("Rejected: invalid heading command.")
                continue

            # Find the aircraft the command is addressed to.
            for aircraft in aircraft_list:
                if aircraft["aircraft_id"] == aircraft_id:

                    # Apply the new heading to the simulation.
                    aircraft["heading"] = float(heading)

                    # Report the successful change.
                    print(
                        f"NEW HEADING: {aircraft_id} -> "
                        f"{float(heading):.1f}° (HMAC=OK)"
                    )

                    # No need to check the remaining aircraft.
                    break

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
            TypeError
        ):
            # Discard messages that cannot be parsed.
            print(f"Ignored invalid message from {address}.")


def run_simulation():
    """Run the aircraft simulation until it is interrupted."""

    # Make sure the database and the initial records exist.
    create_database()
    insert_initial_aircraft()

    # In-memory list of the aircraft that will be moved.
    aircraft_list = []

    # Load the initial state of each aircraft from the database.
    for aircraft_id in AIRCRAFT_IDS:
        aircraft = get_aircraft(aircraft_id)

        # Skip aircraft that are missing from the database.
        if aircraft is None:
            print(f"Aircraft {aircraft_id} not found.")
            continue

        # Copy the data into a dict that is updated in memory.
        aircraft_list.append({
            "aircraft_id": aircraft["aircraft_id"],
            "x": float(aircraft["x"]),
            "y": float(aircraft["y"]),
            "speed": float(aircraft["speed"]),
            "heading": float(aircraft["heading"]),

            # Each aircraft has its own increasing message counter.
            "seq": 0
        })

    # Socket used to send position updates.
    client_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    # Separate socket used to receive commands.
    command_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    # Allow the port to be reused after a quick restart.
    command_socket.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    # Bind the command socket to the command port.
    command_socket.bind((HOST, COMMAND_PORT))

    # Non-blocking mode: the socket never waits for a command,
    # so the simulation keeps moving normally.
    command_socket.setblocking(False)

    print("Aircraft simulation started.")
    print(f"Sending positions to port {PORT}.")
    print(f"Listening for commands on port {COMMAND_PORT}.")
    print("Position messages are signed with HMAC-SHA-256.")
    print("Press Ctrl+C to stop.")

    try:
        # Keep running until the user stops the simulation.
        while True:

            # First check whether the server sent new commands.
            receive_commands(command_socket, aircraft_list)

            # Process every aircraft in turn.
            for aircraft in aircraft_list:

                # Read the current position, speed and heading.
                x = aircraft["x"]
                y = aircraft["y"]
                speed = aircraft["speed"]
                heading = aircraft["heading"]

                # Convert the heading from degrees to radians.
                angle = math.radians(heading)

                # Compute the next position.
                # 0 degrees points to +y and 90 degrees points to +x.
                new_x = x + speed * math.sin(angle)
                new_y = y + speed * math.cos(angle)

                # If the X boundary would be crossed, mirror the
                # heading so the aircraft turns back inside.
                if new_x < MIN_COORDINATE or new_x > MAX_COORDINATE:
                    heading = (360 - heading) % 360

                    # Recompute the position with the new heading.
                    angle = math.radians(heading)
                    new_x = x + speed * math.sin(angle)
                    new_y = y + speed * math.cos(angle)

                # If the Y boundary would be crossed, reverse the
                # vertical component of the movement.
                if new_y < MIN_COORDINATE or new_y > MAX_COORDINATE:
                    heading = (180 - heading) % 360

                    # Recompute the position after the heading change.
                    angle = math.radians(heading)
                    new_x = x + speed * math.sin(angle)
                    new_y = y + speed * math.cos(angle)

                # Store the new position and heading in memory.
                aircraft["x"] = new_x
                aircraft["y"] = new_y
                aircraft["heading"] = heading

                # Increment the message sequence number.
                aircraft["seq"] += 1

                # Build the position update message.
                message = {
                    "type": "POSITION",
                    "aircraft_id": aircraft["aircraft_id"],
                    "seq": aircraft["seq"],
                    "x": new_x,
                    "y": new_y,
                    "speed": speed,
                    "heading": heading
                }

                # Compute the HMAC over the message data, before
                # the hmac field itself is added.
                signature = create_hmac(message)

                # Attach the signature to the message.
                message["hmac"] = signature

                # Serialize the complete message to JSON bytes.
                data = json.dumps(message).encode("utf-8")

                # Send the update to the server over UDP.
                client_socket.sendto(data, (HOST, PORT))

                # Log the transmission to the console.
                print(
                    f"Sent {aircraft['aircraft_id']}: "
                    f"x={new_x:.2f}, y={new_y:.2f}, "
                    f"heading={heading:.1f}°, "
                    f"seq={aircraft['seq']}, HMAC=OK"
                )

            # Wait one second before the next cycle.
            time.sleep(1.0)

    except KeyboardInterrupt:
        # Allow a clean shutdown with Ctrl+C.
        print("\nAircraft simulation stopped.")

    finally:
        # Close both sockets on shutdown.
        client_socket.close()
        command_socket.close()


# Start the simulation only when this file is run directly.
if __name__ == "__main__":
    run_simulation()