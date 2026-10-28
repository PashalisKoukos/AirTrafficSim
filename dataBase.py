# ---------------------------------------------------------
# dataBase.py
# SQLite data access layer for the ATSP system.
# Stores aircraft state and the history of proximity warnings.
#
# Connection handling:
# Each thread lazily opens ONE SQLite connection and reuses it for
# all later queries, instead of opening a new connection per query.
# The database runs in WAL mode so the dashboard (reader) and the
# UDP server (writer) do not block each other.
# ---------------------------------------------------------

import sqlite3
import threading
from datetime import datetime

# Path of the SQLite database file (relative to the working directory).
DB_NAME = "airtraffic.db"

# Thread-local storage: every thread gets its own connection,
# because a SQLite connection must not be shared between threads.
_local = threading.local()


def get_connection():
    """
    Return the SQLite connection of the current thread.

    The connection is created on first use and then reused.
    """

    connection = getattr(_local, "connection", None)

    if connection is None:
        # The timeout makes SQLite wait (instead of failing at once)
        # when another connection is briefly holding a write lock.
        connection = sqlite3.connect(DB_NAME, timeout=5.0)

        # Row factory allows converting each row to a dict by column name.
        connection.row_factory = sqlite3.Row

        # WAL mode lets readers and a writer work concurrently.
        connection.execute("PRAGMA journal_mode=WAL")

        _local.connection = connection

    return connection


def close_connection():
    """Close the connection of the current thread, if one is open."""

    connection = getattr(_local, "connection", None)

    if connection is not None:
        connection.close()
        _local.connection = None


def create_database():
    """Create the database tables if they do not exist yet."""

    connection = get_connection()

    # "with connection" commits on success and rolls back on error.
    with connection:

        # Table holding the current state and static data of each aircraft.
        connection.execute("""
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
        connection.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
                aircraft_id_1 TEXT NOT NULL,
                aircraft_id_2 TEXT NOT NULL,
                distance REAL NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)


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

    connection = get_connection()

    # INSERT OR IGNORE keeps existing rows untouched, so restarting
    # the system does not overwrite the stored positions.
    with connection:
        connection.executemany("""
            INSERT OR IGNORE INTO aircraft (
                aircraft_id, name, x, y, speed, heading,
                origin, destination, manufacturer
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, aircraft_list)

    print("Initial aircraft registered.")


def show_aircraft():
    """Print the contents of the aircraft table to the console."""

    cursor = get_connection().execute("""
        SELECT aircraft_id, name, x, y, speed, heading
        FROM aircraft
        ORDER BY aircraft_id
    """)

    aircraft = cursor.fetchall()

    print("\n--- AIRCRAFT DATABASE ---")

    for plane in aircraft:
        print(
            f"ID: {plane['aircraft_id']} | Name: {plane['name']} | "
            f"Position: ({plane['x']}, {plane['y']}) | "
            f"Speed: {plane['speed']} | Heading: {plane['heading']}"
        )


def get_aircraft(aircraft_id):
    """
    Return one aircraft as a dict, or None if it does not exist.
    """

    cursor = get_connection().execute("""
        SELECT *
        FROM aircraft
        WHERE aircraft_id = ?
    """, (aircraft_id,))

    aircraft = cursor.fetchone()

    if aircraft is None:
        return None

    return dict(aircraft)


def get_all_aircraft():
    """
    Return all aircraft as a list of dicts, ordered by aircraft_id.

    A single query is used, so callers that need every aircraft
    (distance checks, the dashboard) do not query one by one.
    """

    cursor = get_connection().execute("""
        SELECT *
        FROM aircraft
        ORDER BY aircraft_id
    """)

    return [dict(row) for row in cursor.fetchall()]


def update_aircraft_position(aircraft_id, x, y, speed, heading):
    """
    Update the position, speed and heading of an aircraft.

    Returns True if a row was updated, False if the aircraft
    does not exist in the database.
    """

    connection = get_connection()

    with connection:
        cursor = connection.execute("""
            UPDATE aircraft
            SET x = ?, y = ?, speed = ?, heading = ?
            WHERE aircraft_id = ?
        """, (x, y, speed, heading, aircraft_id))

        # rowcount tells us whether any row matched the aircraft_id.
        return cursor.rowcount > 0


def save_warning(aircraft_id_1, aircraft_id_2, distance):
    """Store a proximity warning for a pair of aircraft."""

    # Use the current local system time for the timestamp.
    local_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    connection = get_connection()

    with connection:
        connection.execute("""
            INSERT INTO warnings (
                aircraft_id_1,
                aircraft_id_2,
                distance,
                timestamp
            )
            VALUES (?, ?, ?, ?)
        """, (aircraft_id_1, aircraft_id_2, distance, local_time))


def get_recent_warnings(limit=20):
    """Return the most recent warnings as a list of dicts."""

    cursor = get_connection().execute("""
        SELECT
            warning_id,
            aircraft_id_1,
            aircraft_id_2,
            distance,
            timestamp
        FROM warnings
        ORDER BY warning_id DESC
        LIMIT ?
    """, (limit,))

    return [dict(row) for row in cursor.fetchall()]


def reset_aircraft_positions():
    """
    Restore the initial position and heading of all five aircraft.

    Route data, manufacturer, speed and stored warnings are
    not modified.
    """

    # Initial (id, x, y, heading) values of the five aircraft.
    initial_positions = [
        ("AC001", 10.0, 20.0, 90.0),
        ("AC002", 80.0, 20.0, 270.0),
        ("AC003", 20.0, 80.0, 180.0),
        ("AC004", 70.0, 70.0, 225.0),
        ("AC005", 50.0, 10.0, 0.0)
    ]

    connection = get_connection()

    # Update only the position and heading columns.
    with connection:
        for aircraft_id, x, y, heading in initial_positions:
            connection.execute("""
                UPDATE aircraft
                SET x = ?, y = ?, heading = ?
                WHERE aircraft_id = ?
            """, (x, y, heading, aircraft_id))

    print("Initial aircraft positions restored.")


# When run directly, create the database and show its contents.
if __name__ == "__main__":
    create_database()
    insert_initial_aircraft()
    show_aircraft()
    close_connection()