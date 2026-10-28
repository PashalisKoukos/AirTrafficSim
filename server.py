
# ---------------------------------------------------------
# server.py
# UDP server για το σύστημα AirTrafficSim (ATSP).
#
# Λειτουργίες:
# - Παραλαβή ενημερώσεων θέσης αεροσκαφών.
# - Επαλήθευση HMAC-SHA-256.
# - Έλεγχος εγκυρότητας δεδομένων και αριθμού seq.
# - Ενημέρωση της βάσης δεδομένων.
# - Ανίχνευση μικρών αποστάσεων μεταξύ αεροσκαφών.
# - Αποθήκευση προειδοποιήσεων και αποστολή εντολών αποφυγής.
# ---------------------------------------------------------

# Η socket παρέχει την επικοινωνία μέσω UDP.
import socket

# Η json χρησιμοποιείται για την ανάγνωση και δημιουργία μηνυμάτων JSON.
import json

# Η math χρησιμοποιείται για μαθηματικούς υπολογισμούς και αποστάσεις.
import math

# Η time χρησιμοποιείται για τον χρονικό περιορισμό εντολών αποφυγής.
import time

from security import create_hmac, verify_hmac

# Εισάγουμε τις συναρτήσεις της βάσης δεδομένων.
from dataBase import (
    create_database,
    insert_initial_aircraft,
    update_aircraft_position,
    get_aircraft,
    save_warning
)

# Εισάγουμε τη συνάρτηση επαλήθευσης της υπογραφής HMAC.
from security import verify_hmac


# Διεύθυνση IP στην οποία ακούει ο server.
HOST = "127.0.0.1"

# UDP θύρα για τις ενημερώσεις θέσης.
PORT = 5000

# Θύρα προορισμού για εντολές αλλαγής πορείας.
COMMAND_PORT = 5002

# Αν η απόσταση είναι μικρότερη από αυτή την τιμή,
# καταγράφεται προειδοποίηση και ζητείται αλλαγή πορείας.
# Η τιμή είναι ενδεικτική για την εκπαιδευτική προσομοίωση.
MIN_DISTANCE = 10.0

# Ελάχιστος χρόνος ανάμεσα σε εντολές αποφυγής για το ίδιο ζεύγος.
AVOIDANCE_COOLDOWN = 3.0

# Αποθηκεύουμε τον τελευταίο αποδεκτό αριθμό seq κάθε αεροσκάφους.
last_seq = {}

# Αποθηκεύουμε τη διεύθυνση αποστολής κάθε αεροσκάφους.
aircraft_addresses = {}

# Αποθηκεύουμε την τελευταία χρονική στιγμή αποστολής εντολής αποφυγής.
last_avoidance_time = {}

# Τα αναγνωριστικά των αεροσκαφών της προσομοίωσης.
AIRCRAFT_IDS = ["AC001", "AC002", "AC003", "AC004", "AC005"]


def send_avoidance_command(server_socket, aircraft, other_aircraft):
    """
    Στέλνει υπογεγραμμένη εντολή αλλαγής πορείας σε ένα αεροσκάφος.

    Η εντολή υπογράφεται με HMAC-SHA-256, ώστε το αεροσκάφος
    να μπορεί να ελέγξει την αυθεντικότητά της.
    """

    # Βρίσκουμε τη διεύθυνση του αεροσκάφους.
    address = aircraft_addresses.get(aircraft["aircraft_id"])

    # Αν δεν έχουμε διεύθυνση, δεν μπορούμε να στείλουμε εντολή.
    if address is None:
        return

    # Υπολογίζουμε τη διαφορά των συντεταγμένων των αεροσκαφών.
    dx = aircraft["x"] - other_aircraft["x"]
    dy = aircraft["y"] - other_aircraft["y"]

    # Αν οι θέσεις τους είναι ίδιες, επιλέγουμε εναλλακτική πορεία.
    if dx == 0 and dy == 0:
        new_heading = (aircraft["heading"] + 90) % 360
    else:
        # Υπολογίζουμε την κατεύθυνση απομάκρυνσης.
        # 0° προς +y, 90° προς +x, 180° προς -y, 270° προς -x.
        new_heading = math.degrees(math.atan2(dx, dy)) % 360

    # Δημιουργούμε το μήνυμα της εντολής.
    command = {
        "type": "HEADING",
        "aircraft_id": aircraft["aircraft_id"],
        "heading": new_heading
    }

    # Δημιουργούμε HMAC υπογραφή για το μήνυμα.
    # Η create_hmac βρίσκεται στο security.py.
    signature = create_hmac(command)

    # Προσθέτουμε την υπογραφή στο μήνυμα.
    command["hmac"] = signature

    # Μετατρέπουμε το μήνυμα σε JSON bytes.
    data = json.dumps(command).encode("utf-8")

    # Στέλνουμε την υπογεγραμμένη εντολή στη θύρα του αεροσκάφους.
    command_address = (address[0], COMMAND_PORT)
    server_socket.sendto(data, command_address)

    # Εμφανίζουμε την εντολή στην κονσόλα.
    print(
        f"AVOIDANCE: Εντολή για {aircraft['aircraft_id']} "
        f"-> νέα πορεία {new_heading:.1f}° (HMAC υπογεγραμμένο)"
    )


def check_aircraft_distances(server_socket):
    """
    Ελέγχει τις αποστάσεις μεταξύ των αεροσκαφών.

    Αν δύο αεροσκάφη βρίσκονται πολύ κοντά, αποθηκεύει
    προειδοποίηση και στέλνει εντολές αλλαγής πορείας.
    """

    # Δημιουργούμε λίστα με τις τελευταίες θέσεις των αεροσκαφών.
    aircraft_positions = []

    # Διαβάζουμε κάθε αεροσκάφος από τη βάση δεδομένων.
    for aircraft_id in AIRCRAFT_IDS:
        aircraft = get_aircraft(aircraft_id)

        # Προσθέτουμε στη λίστα όσα αεροσκάφη βρέθηκαν.
        if aircraft is not None:
            aircraft_positions.append(aircraft)

    # Συγκρίνουμε κάθε ζεύγος αεροσκαφών μία φορά.
    for i in range(len(aircraft_positions)):
        for j in range(i + 1, len(aircraft_positions)):

            aircraft_a = aircraft_positions[i]
            aircraft_b = aircraft_positions[j]

            # Υπολογίζουμε τις διαφορές των συντεταγμένων.
            dx = aircraft_a["x"] - aircraft_b["x"]
            dy = aircraft_a["y"] - aircraft_b["y"]

            # Υπολογίζουμε την ευκλείδεια απόσταση.
            distance = math.sqrt(dx ** 2 + dy ** 2)

            # Ελέγχουμε αν η απόσταση είναι μικρότερη από το όριο.
            if distance < MIN_DISTANCE:

                # Εμφανίζουμε την προειδοποίηση.
                print(
                    f"WARNING: Τα αεροσκάφη "
                    f"{aircraft_a['aircraft_id']} και "
                    f"{aircraft_b['aircraft_id']} βρίσκονται πολύ κοντά! "
                    f"Απόσταση: {distance:.2f}"
                )

                # Αποθηκεύουμε την προειδοποίηση στη βάση.
                save_warning(
                    aircraft_a["aircraft_id"],
                    aircraft_b["aircraft_id"],
                    distance
                )

                # Δημιουργούμε σταθερό κλειδί για το ζεύγος αεροσκαφών.
                pair_key = tuple(sorted((
                    aircraft_a["aircraft_id"],
                    aircraft_b["aircraft_id"]
                )))

                # Διαβάζουμε τον τρέχοντα χρόνο.
                now = time.monotonic()

                # Βρίσκουμε πότε στάλθηκε η τελευταία εντολή για το ζεύγος.
                previous_time = last_avoidance_time.get(pair_key, 0)

                # Δεν στέλνουμε εντολές πιο συχνά από το επιτρεπόμενο όριο.
                if now - previous_time >= AVOIDANCE_COOLDOWN:

                    # Ζητάμε από το πρώτο αεροσκάφος να απομακρυνθεί
                    # από το δεύτερο.
                    send_avoidance_command(
                        server_socket,
                        aircraft_a,
                        aircraft_b
                    )

                    # Ζητάμε και από το δεύτερο να απομακρυνθεί
                    # από το πρώτο.
                    send_avoidance_command(
                        server_socket,
                        aircraft_b,
                        aircraft_a
                    )

                    # Καταγράφουμε τον χρόνο αποστολής των εντολών.
                    last_avoidance_time[pair_key] = now


def start_server():
    """
    Αρχικοποιεί τη βάση και ξεκινά τον UDP server.
    """

    # Βεβαιωνόμαστε ότι υπάρχει η βάση δεδομένων.
    create_database()

    # Βεβαιωνόμαστε ότι υπάρχουν οι αρχικές εγγραφές αεροσκαφών.
    insert_initial_aircraft()

    # Δημιουργούμε το UDP socket του server.
    server_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    # Συνδέουμε το socket με την IP και τη θύρα του server.
    server_socket.bind((HOST, PORT))

    print(f"ATSP UDP Server listening on {HOST}:{PORT}")
    print(f"Command destination port: {COMMAND_PORT}")
    print("Αναμονή μηνυμάτων θέσης με επαλήθευση HMAC-SHA-256...")

    try:
        # Ο server παραμένει ενεργός μέχρι να διακοπεί.
        while True:

            # Παραλαμβάνουμε ένα UDP πακέτο και τη διεύθυνση αποστολέα.
            data, address = server_socket.recvfrom(4096)

            try:
                # Μετατρέπουμε τα bytes σε κείμενο UTF-8.
                message_text = data.decode("utf-8")

                # Μετατρέπουμε το JSON σε λεξικό Python.
                message = json.loads(message_text)

                # Δεχόμαστε μόνο JSON αντικείμενα.
                if not isinstance(message, dict):
                    print("Rejected: το μήνυμα δεν είναι JSON object.")
                    continue

                # Διαβάζουμε την υπογραφή που έστειλε το αεροσκάφος.
                received_signature = message.get("hmac")

                # Δημιουργούμε αντίγραφο των δεδομένων χωρίς το πεδίο hmac.
                # Η υπογραφή έχει υπολογιστεί πάνω στα υπόλοιπα πεδία.
                message_to_verify = message.copy()
                message_to_verify.pop("hmac", None)

                # Ελέγχουμε την υπογραφή πριν χρησιμοποιήσουμε τα δεδομένα.
                if not verify_hmac(
                    message_to_verify,
                    received_signature
                ):
                    print(
                        f"Rejected: αποτυχία HMAC από {address}."
                    )
                    continue

                # Από αυτό το σημείο και μετά η υπογραφή είναι έγκυρη.
                # Ελέγχουμε ότι το μήνυμα είναι ενημέρωση θέσης.
                if message_to_verify.get("type") != "POSITION":
                    print("Rejected: μη υποστηριζόμενος τύπος μηνύματος.")
                    continue

                # Διαβάζουμε τα πεδία από το μήνυμα που επαληθεύτηκε.
                aircraft_id = message_to_verify.get("aircraft_id")
                seq = message_to_verify.get("seq")
                x = message_to_verify.get("x")
                y = message_to_verify.get("y")
                speed = message_to_verify.get("speed")
                heading = message_to_verify.get("heading")

                # Ελέγχουμε ότι το ID είναι μη κενό κείμενο.
                if (
                    not isinstance(aircraft_id, str)
                    or not aircraft_id.strip()
                ):
                    print("Rejected: μη έγκυρο aircraft_id.")
                    continue

                # Δεχόμαστε μόνο τα γνωστά αεροσκάφη.
                if aircraft_id not in AIRCRAFT_IDS:
                    print(f"Rejected: άγνωστο αεροσκάφος {aircraft_id}.")
                    continue

                # Ελέγχουμε ότι το seq είναι θετικός ακέραιος.
                # Το type(...) is int αποκλείει τις boolean τιμές.
                if type(seq) is not int or seq < 1:
                    print(f"Rejected: μη έγκυρο seq για {aircraft_id}.")
                    continue

                # Ελέγχουμε ότι οι αριθμητικές τιμές είναι αριθμοί
                # και όχι boolean τιμές.
                numeric_values = (x, y, speed, heading)

                if any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    for value in numeric_values
                ):
                    print(
                        f"Rejected: μη έγκυρα αριθμητικά δεδομένα "
                        f"από {aircraft_id}."
                    )
                    continue

                # Μετατρέπουμε τις αριθμητικές τιμές σε float.
                x = float(x)
                y = float(y)
                speed = float(speed)
                heading = float(heading)

                # Απορρίπτουμε NaN και άπειρες τιμές.
                if not all(
                    math.isfinite(value)
                    for value in (x, y, speed, heading)
                ):
                    print(
                        f"Rejected: μη πεπερασμένες τιμές από {aircraft_id}."
                    )
                    continue

                # Ελέγχουμε ότι οι συντεταγμένες βρίσκονται στην περιοχή.
                if not (
                    0.0 <= x <= 100.0
                    and 0.0 <= y <= 100.0
                ):
                    print(
                        f"Rejected: θέση εκτός ορίων από {aircraft_id}."
                    )
                    continue

                # Η ταχύτητα δεν επιτρέπεται να είναι αρνητική.
                if speed < 0:
                    print(
                        f"Rejected: αρνητική ταχύτητα από {aircraft_id}."
                    )
                    continue

                # Ελέγχουμε ότι η πορεία βρίσκεται μεταξύ 0° και 360°.
                if not 0 <= heading <= 360:
                    print(
                        f"Rejected: μη έγκυρη πορεία από {aircraft_id}."
                    )
                    continue

                # Διαβάζουμε τον τελευταίο αποδεκτό αριθμό seq.
                previous_seq = last_seq.get(aircraft_id, 0)

                # Απορρίπτουμε παλιά ή επαναλαμβανόμενα πακέτα.
                if seq <= previous_seq:
                    print(
                        f"Rejected stale/duplicate packet: {aircraft_id}, "
                        f"seq={seq}, τελευταίο αποδεκτό seq={previous_seq}"
                    )
                    continue

                # Ενημερώνουμε τη βάση με την επαληθευμένη θέση.
                success = update_aircraft_position(
                    aircraft_id,
                    x,
                    y,
                    speed,
                    heading
                )

                # Συνεχίζουμε μόνο αν ενημερώθηκε επιτυχώς η βάση.
                if success:

                    # Αποθηκεύουμε τον τελευταίο αποδεκτό αριθμό seq.
                    last_seq[aircraft_id] = seq

                    # Κρατάμε τη διεύθυνση αποστολής για τις εντολές.
                    aircraft_addresses[aircraft_id] = address

                    # Εμφανίζουμε τα αποδεκτά δεδομένα.
                    print(
                        f"Accepted {aircraft_id}: "
                        f"x={x:.2f}, y={y:.2f}, "
                        f"speed={speed:.2f}, heading={heading:.1f}°, "
                        f"seq={seq}, HMAC=OK"
                    )

                    # Ελέγχουμε τις αποστάσεις μετά την ενημέρωση.
                    check_aircraft_distances(server_socket)

                else:
                    # Η ενημέρωση απέτυχε, π.χ. επειδή το ID
                    # δεν υπάρχει στη βάση δεδομένων.
                    print(f"Rejected: δεν ενημερώθηκε το {aircraft_id}.")

            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                TypeError,
                ValueError
            ):
                # Αν το πακέτο δεν είναι έγκυρο, το απορρίπτουμε
                # χωρίς να σταματήσει ολόκληρος ο server.
                print(f"Rejected: κακοσχηματισμένο πακέτο από {address}.")

    except KeyboardInterrupt:
        # Επιτρέπουμε τον ομαλό τερματισμό με Ctrl+C.
        print("\nServer stopped.")

    finally:
        # Κλείνουμε το socket όταν τερματιστεί ο server.
        server_socket.close()


# Εκκινούμε τον server μόνο όταν εκτελείται απευθείας το αρχείο.
if __name__ == "__main__":
    start_server()
