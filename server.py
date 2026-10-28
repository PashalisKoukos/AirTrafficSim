# ---------------------------------------------------------
# server.py
# UDP server of the AirTrafficSim (ATSP) system.
#
# Responsibilities:
# - Receive aircraft position updates.
# - Verify HMAC-SHA-256 signatures.
# - Validate data and sequence numbers.
# - Update the database.
# - Detect aircraft that are too close to each other.
# - Store warnings and send avoidance commands.
# ---------------------------------------------------------

import json
import math
import socket
import time

# Database functions.
from dataBase import (
    create_database,
    insert_initial_aircraft,
    update_aircraft_position,
    get_aircraft,
    save_warning
)

# HMAC helpers for signing commands and verifying position updates.
from security import create_hmac, verify_hmac


# IP address the server listens on.
HOST = "127.0.0.1"

# UDP port for position updates.
PORT = 5000

# Destination port for heading commands sent to the aircraft.
COMMAND_PORT = 5002

# If the distance between two aircraft is below this value,
# a warning is stored and a heading change is requested.
# The value is illustrative for this educational simulation.
MIN_DISTANCE = 10.0

# Minimum time between avoidance commands for the same pair.
AVOIDANCE_COOLDOWN = 3.0

# Last accepted sequence number of each aircraft.
last_seq = {}

# Source address of each aircraft (used to send commands back).
aircraft_addresses = {}

# Time of the last avoidance command sent for each aircraft pair.
last_avoidance_time = {}

# Identifiers of the simulated aircraft.
AIRCRAFT_IDS = ["AC001", "AC002", "AC003", "AC004", "AC005"]


def send_avoidance_command(server_socket, aircraft, other_aircraft):
    """
    Send a signed heading-change command to one aircraft.

    The command is signed with HMAC-SHA-256 so the aircraft
    can verify its authenticity.
    """

    # Look up the address the aircraft last sent data from.
    address = aircraft_addresses.get(aircraft["aircraft_id"])

    # Without an address the command cannot be delivered.
    if address is None:
        return

    # Difference between the coordinates of the two aircraft.
    dx = aircraft["x"] - other_aircraft["x"]
    dy = aircraft["y"] - other_aircraft["y"]

    # If both aircraft are at the same position, pick an
    # alternative heading by turning 90 degrees.
    if dx == 0 and dy == 0:
        new_heading = (aircraft["heading"] + 90) % 360
    else:
        # Compute the direction pointing away from the other aircraft.
        # 0 deg = +y, 90 deg = +x, 180 deg = -y, 270 deg = -x.
        new_heading = math.degrees(math.atan2(dx, dy)) % 360

    # Build the command message.
    command = {
        "type": "HEADING",
        "aircraft_id": aircraft["aircraft_id"],
        "heading": new_heading
    }

    # Sign the command (create_hmac comes from security.py).
    signature = create_hmac(command)

    # Attach the signature to the message.
    command["hmac"] = signature

    # Serialize the message to JSON bytes.
    data = json.dumps(command).encode("utf-8")

    # Send the signed command to the aircraft's command port.
    command_address = (address[0], COMMAND_PORT)
    server_socket.sendto(data, command_address)

    # Log the command to the console.
    print(
        f"AVOIDANCE: command for {aircraft['aircraft_id']} "
        f"-> new heading {new_heading:.1f}° (HMAC signed)"
    )


def check_aircraft_distances(server_socket):
    """
    Check the distances between all aircraft.

    If two aircraft are too close, a warning is stored and
    avoidance commands are sent to both of them.
    """

    # Latest positions of all aircraft.
    aircraft_positions = []

    # Read each aircraft from the database.
    for aircraft_id in AIRCRAFT_IDS:
        aircraft = get_aircraft(aircraft_id)

        # Keep only the aircraft that were found.
        if aircraft is not None:
            aircraft_positions.append(aircraft)

    # Compare every pair of aircraft exactly once.
    for i in range(len(aircraft_positions)):
        for j in range(i + 1, len(aircraft_positions)):

            aircraft_a = aircraft_positions[i]
            aircraft_b = aircraft_positions[j]

            # Coordinate differences.
            dx = aircraft_a["x"] - aircraft_b["x"]
            dy = aircraft_a["y"] - aircraft_b["y"]

            # Euclidean distance.
            distance = math.sqrt(dx ** 2 + dy ** 2)

            # Check whether the distance is below the limit.
            if distance < MIN_DISTANCE:

                # Report the warning.
                print(
                    f"WARNING: aircraft "
                    f"{aircraft_a['aircraft_id']} and "
                    f"{aircraft_b['aircraft_id']} are too close! "
                    f"Distance: {distance:.2f}"
                )

                # Store the warning in the database.
                save_warning(
                    aircraft_a["aircraft_id"],
                    aircraft_b["aircraft_id"],
                    distance
                )

                # Build an order-independent key for the pair.
                pair_key = tuple(sorted((
                    aircraft_a["aircraft_id"],
                    aircraft_b["aircraft_id"]
                )))

                # Current monotonic time.
                now = time.monotonic()

                # When was the last command sent for this pair?
                previous_time = last_avoidance_time.get(pair_key, 0)

                # Do not send commands more often than allowed.
                if now - previous_time >= AVOIDANCE_COOLDOWN:

                    # Ask the first aircraft to move away from the second.
                    send_avoidance_command(
                        server_socket,
                        aircraft_a,
                        aircraft_b
                    )

                    # Ask the second aircraft to move away from the first.
                    send_avoidance_command(
                        server_socket,
                        aircraft_b,
                        aircraft_a
                    )

                    # Record the time the commands were sent.
                    last_avoidance_time[pair_key] = now


def start_server():
    """
    Initialize the database and run the UDP server.
    """

    # Make sure the database and the initial records exist.
    create_database()
    insert_initial_aircraft()

    # Create the UDP socket of the server.
    server_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    # Bind the socket to the server address and port.
    server_socket.bind((HOST, PORT))

    print(f"ATSP UDP Server listening on {HOST}:{PORT}")
    print(f"Command destination port: {COMMAND_PORT}")
    print("Waiting for position messages with HMAC-SHA-256 verification...")

    try:
        # Keep the server running until it is interrupted.
        while True:

            # Receive one UDP packet and the sender's address.
            data, address = server_socket.recvfrom(4096)

            try:
                # Decode the bytes as UTF-8 text.
                message_text = data.decode("utf-8")

                # Parse the JSON text into a Python object.
                message = json.loads(message_text)

                # Accept only JSON objects.
                if not isinstance(message, dict):
                    print("Rejected: message is not a JSON object.")
                    continue

                # Read the signature sent by the aircraft.
                received_signature = message.get("hmac")

                # Copy the data without the hmac field. The signature
                # was computed over the remaining fields.
                message_to_verify = message.copy()
                message_to_verify.pop("hmac", None)

                # Verify the signature before using any of the data.
                if not verify_hmac(
                    message_to_verify,
                    received_signature
                ):
                    print(f"Rejected: HMAC failure from {address}.")
                    continue

                # The signature is valid from this point on.
                # Check that the message is a position update.
                if message_to_verify.get("type") != "POSITION":
                    print("Rejected: unsupported message type.")
                    continue

                # Read the fields from the verified message.
                aircraft_id = message_to_verify.get("aircraft_id")
                seq = message_to_verify.get("seq")
                x = message_to_verify.get("x")
                y = message_to_verify.get("y")
                speed = message_to_verify.get("speed")
                heading = message_to_verify.get("heading")

                # The ID must be a non-empty string.
                if (
                    not isinstance(aircraft_id, str)
                    or not aircraft_id.strip()
                ):
                    print("Rejected: invalid aircraft_id.")
                    continue

                # Accept only known aircraft.
                if aircraft_id not in AIRCRAFT_IDS:
                    print(f"Rejected: unknown aircraft {aircraft_id}.")
                    continue

                # seq must be a positive integer. Using
                # type(...) is int also rules out booleans.
                if type(seq) is not int or seq < 1:
                    print(f"Rejected: invalid seq for {aircraft_id}.")
                    continue

                # The numeric fields must be numbers, not booleans.
                numeric_values = (x, y, speed, heading)

                if any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    for value in numeric_values
                ):
                    print(
                        f"Rejected: invalid numeric data "
                        f"from {aircraft_id}."
                    )
                    continue

                # Convert the numeric values to float.
                x = float(x)
                y = float(y)
                speed = float(speed)
                heading = float(heading)

                # Reject NaN and infinite values.
                if not all(
                    math.isfinite(value)
                    for value in (x, y, speed, heading)
                ):
                    print(
                        f"Rejected: non-finite values from {aircraft_id}."
                    )
                    continue

                # The coordinates must lie inside the airspace.
                if not (
                    0.0 <= x <= 100.0
                    and 0.0 <= y <= 100.0
                ):
                    print(
                        f"Rejected: position out of bounds "
                        f"from {aircraft_id}."
                    )
                    continue

                # Speed must not be negative.
                if speed < 0:
                    print(
                        f"Rejected: negative speed from {aircraft_id}."
                    )
                    continue

                # Heading must be between 0 and 360 degrees.
                if not 0 <= heading <= 360:
                    print(
                        f"Rejected: invalid heading from {aircraft_id}."
                    )
                    continue

                # Last accepted sequence number for this aircraft.
                previous_seq = last_seq.get(aircraft_id, 0)

                # Reject old or repeated packets (replay protection).
                if seq <= previous_seq:
                    print(
                        f"Rejected stale/duplicate packet: {aircraft_id}, "
                        f"seq={seq}, last accepted seq={previous_seq}"
                    )
                    continue

                # Update the database with the verified position.
                success = update_aircraft_position(
                    aircraft_id,
                    x,
                    y,
                    speed,
                    heading
                )

                # Continue only if the database update succeeded.
                if success:

                    # Remember the last accepted sequence number.
                    last_seq[aircraft_id] = seq

                    # Remember the sender address for later commands.
                    aircraft_addresses[aircraft_id] = address

                    # Log the accepted data.
                    print(
                        f"Accepted {aircraft_id}: "
                        f"x={x:.2f}, y={y:.2f}, "
                        f"speed={speed:.2f}, heading={heading:.1f}°, "
                        f"seq={seq}, HMAC=OK"
                    )

                    # Check distances after the update.
                    check_aircraft_distances(server_socket)

                else:
                    # The update failed, for example because the
                    # ID does not exist in the database.
                    print(f"Rejected: {aircraft_id} was not updated.")

            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                TypeError,
                ValueError
            ):
                # Discard invalid packets without stopping the server.
                print(f"Rejected: malformed packet from {address}.")

    except KeyboardInterrupt:
        # Allow a clean shutdown with Ctrl+C.
        print("\nServer stopped.")

    finally:
        # Close the socket when the server stops.
        server_socket.close()


# Start the server only when this file is run directly.
if __name__ == "__main__":
    start_server()