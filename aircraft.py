
# ---------------------------------------------------------
# aircraft.py
# Προσομοίωση κίνησης αεροσκαφών και επικοινωνίας μέσω UDP.
# Κάθε μήνυμα θέσης προστατεύεται με HMAC-SHA-256.
# ---------------------------------------------------------

# Η math χρησιμοποιείται για τους τριγωνομετρικούς υπολογισμούς.
import math

# Η time επιτρέπει να μεσολαβεί ένα δευτερόλεπτο
# ανάμεσα στις ενημερώσεις θέσης.
import time

# Η socket παρέχει την επικοινωνία μέσω UDP.
import socket

import math
from security import create_hmac, verify_hmac

# Η json μετατρέπει τα μηνύματα σε μορφή JSON.
import json

# Εισάγουμε συναρτήσεις για τη δημιουργία της βάσης
# και την ανάγνωση των αρχικών στοιχείων των αεροσκαφών.
from dataBase import (
    create_database,
    insert_initial_aircraft,
    get_aircraft
)

# Εισάγουμε τη συνάρτηση δημιουργίας ψηφιακής υπογραφής HMAC.
from security import create_hmac


# Διεύθυνση IP του server.
HOST = "127.0.0.1"

# Θύρα στην οποία στέλνουμε τις ενημερώσεις θέσης.
PORT = 5000

# Θύρα στην οποία περιμένουμε εντολές αλλαγής πορείας.
COMMAND_PORT = 5002

# Όρια της περιοχής στην οποία κινούνται τα αεροσκάφη.
MIN_COORDINATE = 0.0
MAX_COORDINATE = 100.0

# Τα αναγνωριστικά των πέντε αεροσκαφών της προσομοίωσης.
AIRCRAFT_IDS = ["AC001", "AC002", "AC003", "AC004", "AC005"]


def receive_commands(command_socket, aircraft_list):
    """
    Ελέγχει τις εντολές που λαμβάνονται από τον server.

    Πριν εφαρμοστεί μια εντολή HEADING, επαληθεύεται
    η υπογραφή HMAC-SHA-256.
    """

    # Διαβάζουμε όλα τα διαθέσιμα μηνύματα UDP.
    while True:
        try:
            # Παραλαμβάνουμε ένα UDP πακέτο από τον server.
            data, address = command_socket.recvfrom(4096)

        except BlockingIOError:
            # Δεν υπάρχουν άλλα μηνύματα αυτή τη στιγμή.
            break

        try:
            # Μετατρέπουμε τα bytes σε λεξικό Python.
            command = json.loads(data.decode("utf-8"))

            # Δεχόμαστε μόνο μηνύματα JSON που είναι λεξικά.
            if not isinstance(command, dict):
                continue

            # Διαβάζουμε την υπογραφή που έστειλε ο server.
            received_signature = command.get("hmac")

            # Αν δεν υπάρχει υπογραφή, απορρίπτουμε την εντολή.
            if not isinstance(received_signature, str):
                print("Rejected: η εντολή δεν έχει HMAC.")
                continue

            # Δημιουργούμε αντίγραφο του μηνύματος για επαλήθευση.
            # Αφαιρούμε το hmac, επειδή δεν περιλαμβάνεται
            # στα δεδομένα που υπογράφηκαν αρχικά.
            command_to_verify = command.copy()
            command_to_verify.pop("hmac")

            # Επαληθεύουμε ότι η υπογραφή είναι έγκυρη.
            if not verify_hmac(command_to_verify, received_signature):
                print("Rejected: αποτυχία επαλήθευσης HMAC.")
                continue

            # Από εδώ και κάτω επεξεργαζόμαστε μόνο
            # εντολές με έγκυρη υπογραφή.
            if command.get("type") != "HEADING":
                continue

            # Διαβάζουμε το ID του αεροσκάφους και τη νέα πορεία.
            aircraft_id = command.get("aircraft_id")
            heading = command.get("heading")

            # Ελέγχουμε ότι η πορεία είναι έγκυρος αριθμός.
            if (
                isinstance(heading, bool)
                or not isinstance(heading, (int, float))
                or not math.isfinite(heading)
                or not 0 <= heading < 360
            ):
                print("Rejected: μη έγκυρη εντολή πορείας.")
                continue

            # Εντοπίζουμε το αεροσκάφος στο οποίο απευθύνεται η εντολή.
            for aircraft in aircraft_list:
                if aircraft["aircraft_id"] == aircraft_id:

                    # Εφαρμόζουμε τη νέα πορεία στην προσομοίωση.
                    aircraft["heading"] = float(heading)

                    # Εμφανίζουμε την επιτυχημένη αλλαγή.
                    print(
                        f"ΝΕΑ ΠΟΡΕΙΑ: {aircraft_id} -> "
                        f"{float(heading):.1f}° (HMAC=OK)"
                    )

                    # Δεν χρειάζεται να ελέγξουμε άλλα αεροσκάφη.
                    break

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
            TypeError
        ):
            # Αν το μήνυμα δεν είναι έγκυρο, το απορρίπτουμε.
            print(f"Αγνοήθηκε μη έγκυρο μήνυμα από {address}.")

def run_simulation():
    # Βεβαιωνόμαστε ότι υπάρχει η βάση δεδομένων.
    create_database()

    # Βεβαιωνόμαστε ότι υπάρχουν οι αρχικές εγγραφές των αεροσκαφών.
    insert_initial_aircraft()

    # Αποθηκεύουμε προσωρινά στη μνήμη τα αεροσκάφη που θα κινούνται.
    aircraft_list = []

    # Διαβάζουμε τα αρχικά στοιχεία κάθε αεροσκάφους από τη βάση.
    for aircraft_id in AIRCRAFT_IDS:
        aircraft = get_aircraft(aircraft_id)

        # Αν δεν υπάρχει το αεροσκάφος στη βάση, το παραλείπουμε.
        if aircraft is None:
            print(f"Aircraft {aircraft_id} not found.")
            continue

        # Αντιγράφουμε τα δεδομένα σε λεξικό που θα ενημερώνεται στη μνήμη.
        aircraft_list.append({
            "aircraft_id": aircraft["aircraft_id"],
            "x": float(aircraft["x"]),
            "y": float(aircraft["y"]),
            "speed": float(aircraft["speed"]),
            "heading": float(aircraft["heading"]),

            # Κάθε αεροσκάφος έχει δική του αύξουσα αρίθμηση μηνυμάτων.
            "seq": 0
        })

    # Δημιουργούμε το socket αποστολής ενημερώσεων θέσης.
    client_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    # Δημιουργούμε ξεχωριστό socket για την παραλαβή εντολών.
    command_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    # Επιτρέπουμε την επαναχρησιμοποίηση της θύρας
    # σε περιπτώσεις γρήγορης επανεκκίνησης.
    command_socket.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    # Συνδέουμε το socket εντολών στη θύρα 5002.
    command_socket.bind((HOST, COMMAND_PORT))

    # Το socket δεν θα περιμένει επ' αόριστον για μια εντολή.
    # Έτσι η προσομοίωση θα συνεχίζει να κινείται κανονικά.
    command_socket.setblocking(False)

    print("Aircraft simulation started.")
    print(f"Αποστολή θέσεων στη θύρα {PORT}.")
    print(f"Αναμονή εντολών στη θύρα {COMMAND_PORT}.")
    print("Τα μηνύματα θέσης υπογράφονται με HMAC-SHA-256.")
    print("Press Ctrl+C to stop.")

    try:
        # Συνεχίζουμε μέχρι ο χρήστης να σταματήσει την προσομοίωση.
        while True:

            # Ελέγχουμε πρώτα αν ο server έστειλε νέες εντολές.
            receive_commands(command_socket, aircraft_list)

            # Επεξεργαζόμαστε διαδοχικά όλα τα αεροσκάφη.
            for aircraft in aircraft_list:

                # Διαβάζουμε την τρέχουσα θέση, ταχύτητα και πορεία.
                x = aircraft["x"]
                y = aircraft["y"]
                speed = aircraft["speed"]
                heading = aircraft["heading"]

                # Μετατρέπουμε την πορεία από μοίρες σε ακτίνια.
                angle = math.radians(heading)

                # Υπολογίζουμε την επόμενη θέση.
                # 0° σημαίνει προς +y και 90° προς +x.
                new_x = x + speed * math.sin(angle)
                new_y = y + speed * math.cos(angle)

                # Αν ξεπεραστεί το όριο στον άξονα X,
                # αλλάζουμε την πορεία ώστε να κινηθούμε προς τα μέσα.
                if new_x < MIN_COORDINATE or new_x > MAX_COORDINATE:
                    heading = (360 - heading) % 360

                    # Υπολογίζουμε ξανά τη θέση με τη νέα πορεία.
                    angle = math.radians(heading)
                    new_x = x + speed * math.sin(angle)
                    new_y = y + speed * math.cos(angle)

                # Αν ξεπεραστεί το όριο στον άξονα Y,
                # αντιστρέφουμε την κατακόρυφη συνιστώσα της κίνησης.
                if new_y < MIN_COORDINATE or new_y > MAX_COORDINATE:
                    heading = (180 - heading) % 360

                    # Υπολογίζουμε ξανά τη θέση μετά την αλλαγή πορείας.
                    angle = math.radians(heading)
                    new_x = x + speed * math.sin(angle)
                    new_y = y + speed * math.cos(angle)

                # Ενημερώνουμε τη θέση και την πορεία στη μνήμη.
                aircraft["x"] = new_x
                aircraft["y"] = new_y
                aircraft["heading"] = heading

                # Αυξάνουμε τον αριθμό του μηνύματος.
                aircraft["seq"] += 1

                # Δημιουργούμε το μήνυμα ενημέρωσης θέσης.
                message = {
                    "type": "POSITION",
                    "aircraft_id": aircraft["aircraft_id"],
                    "seq": aircraft["seq"],
                    "x": new_x,
                    "y": new_y,
                    "speed": speed,
                    "heading": heading
                }

                # Υπολογίζουμε την υπογραφή HMAC πάνω στα δεδομένα
                # του μηνύματος, πριν προσθέσουμε το πεδίο hmac.
                signature = create_hmac(message)

                # Προσθέτουμε την υπογραφή στο μήνυμα.
                message["hmac"] = signature

                # Μετατρέπουμε το πλήρες μήνυμα σε JSON bytes.
                data = json.dumps(message).encode("utf-8")

                # Στέλνουμε την ενημέρωση στον server μέσω UDP.
                client_socket.sendto(data, (HOST, PORT))

                # Εμφανίζουμε την αποστολή στην κονσόλα.
                print(
                    f"Sent {aircraft['aircraft_id']}: "
                    f"x={new_x:.2f}, y={new_y:.2f}, "
                    f"heading={heading:.1f}°, "
                    f"seq={aircraft['seq']}, HMAC=OK"
                )

            # Περιμένουμε ένα δευτερόλεπτο πριν από τον επόμενο κύκλο.
            time.sleep(1.0)

    except KeyboardInterrupt:
        # Επιτρέπουμε την ομαλή διακοπή με Ctrl+C.
        print("\nAircraft simulation stopped.")

    finally:
        # Κλείνουμε και τα δύο sockets κατά τον τερματισμό.
        client_socket.close()
        command_socket.close()


# Εκκινούμε την προσομοίωση μόνο όταν εκτελείται αυτό το αρχείο απευθείας.
if __name__ == "__main__":
    run_simulation()
