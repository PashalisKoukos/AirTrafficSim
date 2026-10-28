
import sqlite3
from datetime import datetime
DB_NAME = "airtraffic.db"


def create_database():
    connection = sqlite3.connect(DB_NAME)

    cursor = connection.cursor()

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

    # Δημιουργούμε πίνακα για την αποθήκευση των προειδοποιήσεων.
    # Κάθε εγγραφή αντιστοιχεί σε ένα περιστατικό επικίνδυνης εγγύτητας.
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS warnings
                   (
                       warning_id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       aircraft_id_1
                       TEXT
                       NOT
                       NULL,
                       aircraft_id_2
                       TEXT
                       NOT
                       NULL,
                       distance
                       REAL
                       NOT
                       NULL,
                       timestamp
                       DATETIME
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   """)

    connection.commit()
    connection.close()

def insert_initial_aircraft():
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

        cursor.executemany("""
                           INSERT
                           OR IGNORE INTO aircraft (
                aircraft_id, name, x, y, speed, heading,
                origin, destination, manufacturer
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                           """, aircraft_list)

        connection.commit()
        connection.close()

        print("Τα αρχικά αεροσκάφη καταχωρίστηκαν!")

def show_aircraft():
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
    connection = sqlite3.connect(DB_NAME)
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
    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE aircraft
        SET x = ?, y = ?, speed = ?, heading = ?
        WHERE aircraft_id = ?
    """, (x, y, speed, heading, aircraft_id))

    updated = cursor.rowcount > 0

    connection.commit()
    connection.close()

    return updated

def save_warning(aircraft_id_1, aircraft_id_2, distance):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Παίρνουμε την τρέχουσα τοπική ώρα του συστήματος
    local_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute("""
        INSERT INTO warnings (
            aircraft_id_1,
            aircraft_id_2,
            distance,
            timestamp
        )
        VALUES (?, ?, ?, ?)
    """, (aircraft_id_1, aircraft_id_2, distance, local_time))

    conn.commit()
    conn.close()


def reset_aircraft_positions():
    # Συνδέουμε τη συνάρτηση με την υπάρχουσα βάση δεδομένων.
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Ορίζουμε τις αρχικές θέσεις και πορείες των πέντε αεροσκαφών.
    # Δεν αλλάζουμε τα στοιχεία διαδρομής, κατασκευαστή ή τις προειδοποιήσεις.
    initial_positions = [
        ("AC001", 10.0, 20.0, 90.0),
        ("AC002", 80.0, 20.0, 270.0),
        ("AC003", 20.0, 80.0, 180.0),
        ("AC004", 70.0, 70.0, 225.0),
        ("AC005", 50.0, 10.0, 0.0)
    ]

    # Ενημερώνουμε μόνο τις στήλες θέσης και πορείας κάθε αεροσκάφους.
    for aircraft_id, x, y, heading in initial_positions:
        cursor.execute(
            """
            UPDATE aircraft
            SET x = ?, y = ?, heading = ?
            WHERE aircraft_id = ?
            """,
            (x, y, heading, aircraft_id)
        )

    # Αποθηκεύουμε τις αλλαγές και κλείνουμε τη σύνδεση με τη βάση.
    conn.commit()
    conn.close()

    print("Οι αρχικές θέσεις των αεροσκαφών επαναφέρθηκαν.")


if __name__ == "__main__":
    create_database()
    insert_initial_aircraft()
    show_aircraft()




