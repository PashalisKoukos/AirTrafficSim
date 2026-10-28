# ---------------------------------------------------------
# dataBase.py
# SQLite data access layer for the ATSP system.
# Stores aircraft state and the history of proximity warnings.
# ---------------------------------------------------------

import sqlite3
from datetime import datetime

# Path of the SQLite database file (relative to the working directory).
DB_NAME = "airtraffic.db"


def create_database():
    """Create the database tables if they do not exist yet."""

    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    # Table holding the current state and static data of each aircraft.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aircraft (
            aircraft_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            x REAL NOT NULL,
            y REAL NOT NULL,
            speed REAL NOT NULL,
            heading REAL NOT NULL,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            manufacturer TEXT NOT NULL
        )
    """)

    # Table storing proximity warnings.
    # Each row represents one dangerous-proximity incident.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
            aircraft_id_1 TEXT NOT NULL,
            aircraft_id_2 TEXT NOT NULL,
            distance REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


def insert_initial_aircraft():
    """Insert the five initial aircraft (existing rows are kept)."""

    # Each tuple: id, name, x, y, speed, heading,
    #             origin, destination, manufacturer.
    aircraft_list = [
        ("AC001", "Aegean-01", 10.0, 20.0, 2.0, 90.0,
         "ATH", "SKG", "Airbus"),

        ("AC002", "Aegean-02", 80.0, 20.0, 2.0, 270.0,
         "SKG", "ATH", "Airbus"),

        ("AC003", "Sky-03", 20.0, 80.0, 1.5, 180.0,
         "HER", "ATH", "Boeing"),

        ("AC004", "Sky-04", 70.0, 70.0, 1.8, 225.0,
         "RHO", "ATH", "Boeing"),

        ("AC005", "Sky-05", 50.0, 10.0, 1.2, 0.0,
         "ATH", "JTR", "Embraer")
    ]

    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    # INSERT OR IGNORE keeps existing rows untouched, so restarting
    # the system does not overwrite the stored positions.
    cursor.executemany("""
        INSERT OR IGNORE INTO aircraft (
            aircraft_id, name, x, y, speed, heading,
            origin, destination, manufacturer
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, aircraft_list)

    connection.commit()
    connection.close()

    print("Initial aircraft registered.")


def show_aircraft():
    """Print the contents of the aircraft table to the console."""

    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT aircraft_id, name, x, y, speed, heading
        FROM aircraft
        ORDER BY aircraft_id
    """)

    aircraft = cursor.fetchall()
    connection.close()

    print("\n--- AIRCRAFT DATABASE ---")

    for plane in aircraft:
        print(
            f"ID: {plane[0]} | Name: {plane[1]} | "
            f"Position: ({plane[2]}, {plane[3]}) | "
            f"Speed: {plane[4]} | Heading: {plane[5]}"
        )


def get_aircraft(aircraft_id):
    """
    Return one aircraft as a dict, or None if it does not exist.
    """

    connection = sqlite3.connect(DB_NAME)

    # Row factory allows converting each row to a dict by column name.
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM aircraft
        WHERE aircraft_id = ?
    """, (aircraft_id,))

    aircraft = cursor.fetchone()
    connection.close()

    if aircraft is None:
        return None

    return dict(aircraft)


def update_aircraft_position(aircraft_id, x, y, speed, heading):
    """
    Update the position, speed and heading of an aircraft.

    Returns True if a row was updated, False if the aircraft
    does not exist in the database.
    """

    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE aircraft
        SET x = ?, y = ?, speed = ?, heading = ?
        WHERE aircraft_id = ?
    """, (x, y, speed, heading, aircraft_id))

    # rowcount tells us whether any row matched the aircraft_id.
    updated = cursor.rowcount > 0

    connection.commit()
    connection.close()

    return updated


def save_warning(aircraft_id_1, aircraft_id_2, distance):
    """Store a proximity warning for a pair of aircraft."""

    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    # Use the current local system time for the timestamp.
    local_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO warnings (
            aircraft_id_1,
            aircraft_id_2,
            distance,
            timestamp
        )
        VALUES (?, ?, ?, ?)
    """, (aircraft_id_1, aircraft_id_2, distance, local_time))

    connection.commit()
    connection.close()


def reset_aircraft_positions():
    """
    Restore the initial position and heading of all five aircraft.

    Route data, manufacturer, speed and stored warnings are
    not modified.
    """

    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    # Initial (id, x, y, heading) values of the five aircraft.
    initial_positions = [
        ("AC001", 10.0, 20.0, 90.0),
        ("AC002", 80.0, 20.0, 270.0),
        ("AC003", 20.0, 80.0, 180.0),
        ("AC004", 70.0, 70.0, 225.0),
        ("AC005", 50.0, 10.0, 0.0)
    ]

    # Update only the position and heading columns.
    for aircraft_id, x, y, heading in initial_positions:
        cursor.execute("""
            UPDATE aircraft
            SET x = ?, y = ?, heading = ?
            WHERE aircraft_id = ?
        """, (x, y, heading, aircraft_id))

    connection.commit()
    connection.close()

    print("Initial aircraft positions restored.")


# When run directly, create the database and show its contents.
if __name__ == "__main__":
    create_database()
    insert_initial_aircraft()
    show_aircraft()