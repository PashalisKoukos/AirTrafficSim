
import socket
import json

# Εισάγουμε τη συνάρτηση που διαβάζει στοιχεία αεροσκάφους
# από τη βάση δεδομένων SQLite.
from dataBase import get_aircraft


# Διεύθυνση IP και θύρα στην οποία ακούει ο UDP server.
SERVER_IP = "127.0.0.1"
SERVER_PORT = 5000

# Διαβάζουμε τα τρέχοντα στοιχεία του δεύτερου αεροσκάφους.
# Θα χρησιμοποιήσουμε τη θέση του για να τοποθετήσουμε
# το πρώτο αεροσκάφος ακριβώς στο ίδιο σημείο.
aircraft_b = get_aircraft("AC002")

# Ελέγχουμε ότι το αεροσκάφος υπάρχει στη βάση.
if aircraft_b is None:
    print("Σφάλμα: Το AC002 δεν βρέθηκε στη βάση δεδομένων.")

else:
    # Δημιουργούμε ένα μήνυμα θέσης για το AC001.
    # Οι συντεταγμένες είναι ίδιες με εκείνες του AC002,
    # επομένως η απόσταση των δύο αεροσκαφών θα είναι μηδέν.
    message = {
        "type": "POSITION",
        "aircraft_id": "AC001",
        "seq": 1,
        "x": aircraft_b["x"],
        "y": aircraft_b["y"],
        "speed": 2.0,
        "heading": 90.0
    }

    # Μετατρέπουμε το λεξικό σε JSON και έπειτα σε bytes,
    # επειδή τα UDP datagrams μεταφέρουν δεδομένα ως bytes.
    data = json.dumps(message).encode("utf-8")

    # Δημιουργούμε UDP socket για την αποστολή του μηνύματος.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:

        # Στέλνουμε το μήνυμα στον server.
        sock.sendto(data, (SERVER_IP, SERVER_PORT))

    # Ενημερώνουμε τον χρήστη ότι το πακέτο στάλθηκε.
    print("Στάλθηκε δοκιμαστική θέση του AC001:", message)
