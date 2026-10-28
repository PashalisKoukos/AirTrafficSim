
# security.py
# ---------------------------------------------------------
# Το αρχείο αυτό παρέχει προστασία των μηνυμάτων UDP
# με χρήση HMAC-SHA-256.
#
# Το μυστικό κλειδί αποθηκεύεται στο αρχείο .env και
# δεν γράφεται απευθείας στον πηγαίο κώδικα.
# ---------------------------------------------------------

import hashlib
import hmac
import json
import os

from dotenv import load_dotenv


# Φορτώνουμε τις μεταβλητές που υπάρχουν στο αρχείο .env.
load_dotenv()


# Διαβάζουμε το μυστικό κλειδί από τη μεταβλητή περιβάλλοντος.
secret_key = os.getenv("ATSP_HMAC_KEY")


# Αν δεν βρεθεί το κλειδί, σταματάμε με κατανοητό μήνυμα.
if not secret_key:
    raise RuntimeError(
        "Δεν βρέθηκε το ATSP_HMAC_KEY. "
        "Έλεγξε ότι υπάρχει το αρχείο .env "
        "και ότι περιέχει το μυστικό κλειδί."
    )


# Μετατρέπουμε το κλειδί από κείμενο σε bytes,
# όπως απαιτείται από τη συνάρτηση HMAC.
HMAC_SECRET_KEY = secret_key.encode("utf-8")


def create_hmac(message):
    """
    Δημιουργεί ψηφιακή υπογραφή HMAC-SHA-256 για ένα μήνυμα.

    Το message πρέπει να είναι λεξικό Python (dict).
    Η υπογραφή δημιουργείται από τα δεδομένα του μηνύματος,
    ώστε ο παραλήπτης να μπορεί να ελέγξει αν αλλοιώθηκαν.
    """

    # Μετατρέπουμε το λεξικό σε JSON με σταθερή σειρά κλειδιών.
    # Έτσι, ίδιο μήνυμα παράγει ίδια bytes και στις δύο πλευρές.
    message_json = json.dumps(
        message,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False
    )

    # Μετατρέπουμε το JSON σε bytes.
    message_bytes = message_json.encode("utf-8")

    # Δημιουργούμε την υπογραφή με HMAC και SHA-256.
    signature = hmac.new(
        HMAC_SECRET_KEY,
        message_bytes,
        hashlib.sha256
    ).hexdigest()

    # Επιστρέφουμε την υπογραφή ως δεκαεξαδικό κείμενο.
    return signature


def verify_hmac(message, received_signature):
    """
    Ελέγχει αν η υπογραφή που έλαβε ο server
    αντιστοιχεί στο συγκεκριμένο μήνυμα.

    Επιστρέφει:
        True  -> η υπογραφή είναι έγκυρη
        False -> η υπογραφή είναι λανθασμένη ή τα δεδομένα
                 δεν μπορούν να υπογραφούν
    """

    # Η υπογραφή που λάβαμε πρέπει να είναι κείμενο.
    if not isinstance(received_signature, str):
        return False

    try:
        # Υπολογίζουμε ξανά την αναμενόμενη υπογραφή.
        expected_signature = create_hmac(message)

        # Συγκρίνουμε τις υπογραφές με ασφαλή τρόπο.
        # Η compare_digest αποφεύγει ορισμένες επιθέσεις
        # που βασίζονται στον χρόνο σύγκρισης.
        return hmac.compare_digest(
            expected_signature,
            received_signature
        )

    except (TypeError, ValueError):
        # Αν το μήνυμα δεν μπορεί να μετατραπεί σωστά σε JSON,
        # το θεωρούμε μη έγκυρο.
        return False
