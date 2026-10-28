# ---------------------------------------------------------
# main.py
# Single entry point of the AirTrafficSim (ATSP) system.
# Runs the UDP server, the aircraft simulation and the web
# dashboard concurrently, each in its own thread.
# ---------------------------------------------------------

import threading
import time

# Import the start-up functions from the other modules.
from server import start_server
from aircraft import run_simulation
from app import app


def run_flask_dashboard():
    """
    Start the Flask web server.

    debug=False and use_reloader=False are important here: the
    reloader would spawn an additional process and duplicate the
    background threads.
    """
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=False,
        use_reloader=False
    )


if __name__ == "__main__":
    print("=" * 60)
    print("  STARTING AIR TRAFFIC SIMULATION (ATSP)")
    print("=" * 60)

    # Daemon threads are stopped automatically when the main
    # thread exits, so Ctrl+C shuts everything down cleanly.

    # 1. Thread for the UDP server.
    server_thread = threading.Thread(
        target=start_server,
        daemon=True
    )

    # 2. Thread for the aircraft simulation.
    simulation_thread = threading.Thread(
        target=run_simulation,
        daemon=True
    )

    # 3. Thread for the web dashboard (Flask).
    dashboard_thread = threading.Thread(
        target=run_flask_dashboard,
        daemon=True
    )

    try:
        # Start the server first so its port is open before
        # the aircraft begin sending data.
        print("[*] Starting UDP server...")
        server_thread.start()

        # Short pause to give the server time to bind its port.
        time.sleep(1)

        print("[*] Starting aircraft simulation...")
        simulation_thread.start()

        print("[*] Starting web dashboard (http://127.0.0.1:5001)...")
        dashboard_thread.start()

        print("-" * 60)
        print("  All subsystems are running.")
        print("  Press Ctrl+C in the terminal to stop.")
        print("-" * 60)

        # Keep the main thread alive so the daemon threads keep running.
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[!] Shutting down AirTrafficSim...")
        print("Goodbye!")