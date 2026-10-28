# ---------------------------------------------------------
# main.py
# Κεντρικό σημείο εκκίνησης ολόκληρου του συστήματος AirTrafficSim.
# Εκτελεί παράλληλα τον Server, τα Αεροσκάφη και το Web Dashboard.
# ---------------------------------------------------------

import threading
import time

# Εισάγουμε τις βασικές συναρτήσεις εκκίνησης από τα άλλα αρχεία
from server import start_server
from aircraft import run_simulation
from app import app


def run_flask_dashboard():
    """
    Ξεκινά τον web server του Flask.
    Σημαντικό: Βάζουμε debug=False και use_reloader=False
    για να μην δημιουργούνται διπλά threads/processes στο παρασκήνιο.
    """
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=False,
        use_reloader=False
    )


if __name__ == "__main__":
    print("=" * 60)
    print("  ΕΚΚΙΝΗΣΗ ΣΥΣΤΗΜΑΤΟΣ AIR TRAFFIC SIMULATION (ATSP)")
    print("=" * 60)

    # 1. Δημιουργούμε ξεχωριστό thread για τον Server
    server_thread = threading.Thread(
        target=start_server,
        daemon=True
    )

    # 2. Δημιουργούμε ξεχωριστό thread για την προσομοίωση αεροσκαφών
    simulation_thread = threading.Thread(
        target=run_simulation,
        daemon=True
    )

    # 3. Δημιουργούμε ξεχωριστό thread για το Web Dashboard (Flask)
    dashboard_thread = threading.Thread(
        target=run_flask_dashboard,
        daemon=True
    )

    try:
        # Ξεκινάμε τον Server πρώτα
        print("[*] Εκκίνηση UDP Server...")
        server_thread.start()
        time.sleep(1)  # Μικρή παύση για να προλάβει να ανοίξει η θύρα

        # Ξεκινάμε την προσομοίωση των αεροσκαφών
        print("[*] Εκκίνηση προσομοίωσης αεροσκαφών...")
        simulation_thread.start()

        # Ξεκινάμε το Web Dashboard
        print("[*] Εκκίνηση Web Dashboard (http://127.0.0.1:5001)...")
        dashboard_thread.start()

        print("-" * 60)
        print("  Όλα τα υποσυστήματα λειτουργούν επιτυχώς!")
        print("  Πατήστε Ctrl+C στο τερματικό για τερματισμό.")
        print("-" * 60)

        # Κρατάμε το κεντρικό νήμα ζωντανό ώστε να τρέχουν τα threads
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[!] Γίνεται τερματισμός του συστήματος AirTrafficSim...")
        print("Αντίο!")