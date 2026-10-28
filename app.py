import json
import socket

# ================================================================
# AirTrafficSim — Air Traffic Control Dashboard
# ================================================================
# Τι προσφέρει αυτή η εφαρμογή:
# 1. Εμφανίζει έναν σύγχρονο πίνακα ελέγχου εναέριας κυκλοφορίας.
# 2. Διαβάζει τις θέσεις των αεροσκαφών από τη βάση SQLite.
# 3. Σχεδιάζει τα αεροσκάφη σε έναν δυναμικό δισδιάστατο χάρτη.
# 4. Υπολογίζει τις τρέχουσες αποστάσεις μεταξύ των αεροσκαφών.
# 5. Επισημαίνει με κόκκινο χρώμα τα αεροσκάφη σε κίνδυνο.
# 6. Εμφανίζει στατιστικά, στοιχεία πτήσεων και προειδοποιήσεις.
# 7. Ανανεώνει αυτόματα την οθόνη κάθε δύο δευτερόλεπτα.
#
# Σημαντικό:
# Η εφαρμογή χρησιμοποιεί το υπάρχον dataBase.py και τη βάση
# airtraffic.db. Δεν αντικαθιστά τον UDP server ή την προσομοίωση.
# ================================================================

from flask import Flask, render_template_string, jsonify
import sqlite3
import math

# Εισάγουμε το όνομα της βάσης από το υπάρχον αρχείο μας.
from dataBase import DB_NAME


# ------------------------------------------------
# 1. Ρυθμίσεις εφαρμογής
# ------------------------------------------------

# Δημιουργούμε την εφαρμογή Flask.
app = Flask(__name__)

# Ελάχιστη επιτρεπόμενη απόσταση σε μονάδες του μοντέλου.
# Πρέπει να συμφωνεί με το MIN_DISTANCE του server.py.
MIN_DISTANCE = 10.0

# Διάστημα αυτόματης ανανέωσης σε χιλιοστά του δευτερολέπτου.
REFRESH_INTERVAL = 2000


# ------------------------------------------------
# 2. Ανάγνωση δεδομένων αεροσκαφών από τη SQLite
# ------------------------------------------------
def get_aircraft_data():
    """
    Διαβάζει τα στοιχεία όλων των αεροσκαφών από τη βάση.

    Επιστρέφει μια λίστα από λεξικά, ώστε τα δεδομένα να
    μπορούν να μετατραπούν εύκολα σε JSON για το dashboard.
    """

    # Ανοίγουμε σύνδεση με τη βάση δεδομένων.
    connection = sqlite3.connect(DB_NAME)

    # Κάθε γραμμή θα μπορεί να μετατραπεί σε λεξικό
    # με κλειδιά τα ονόματα των στηλών.
    connection.row_factory = sqlite3.Row

    try:
        cursor = connection.cursor()

        # Διαβάζουμε όλα τα πεδία που χρειαζόμαστε
        # για τον χάρτη και τον πίνακα πτήσεων.
        cursor.execute("""
            SELECT
                aircraft_id,
                name,
                x,
                y,
                speed,
                heading,
                origin,
                destination,
                manufacturer
            FROM aircraft
            ORDER BY aircraft_id
        """)

        # Μετατρέπουμε τις γραμμές σε κανονικά λεξικά Python.
        return [dict(row) for row in cursor.fetchall()]

    finally:
        # Κλείνουμε πάντα τη σύνδεση, ακόμη κι αν παρουσιαστεί σφάλμα.
        connection.close()


# ------------------------------------------------
# 3. Ανάγνωση ιστορικών προειδοποιήσεων από τη SQLite
# ------------------------------------------------
def get_warning_data():
    """
    Διαβάζει τις 20 πιο πρόσφατες προειδοποιήσεις που
    αποθηκεύτηκαν από τον server.
    """

    connection = sqlite3.connect(DB_NAME)
    connection.row_factory = sqlite3.Row

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                warning_id,
                aircraft_id_1,
                aircraft_id_2,
                distance,
                timestamp
            FROM warnings
            ORDER BY warning_id DESC
            LIMIT 20
        """)

        return [dict(row) for row in cursor.fetchall()]

    finally:
        connection.close()


# ------------------------------------------------
# 4. Υπολογισμός τρέχουσας απόστασης μεταξύ αεροσκαφών
# ------------------------------------------------
def calculate_active_conflicts(aircraft):
    """
    Ελέγχει όλες τις δυνατές δυάδες αεροσκαφών.

    Αν η απόσταση δύο αεροσκαφών είναι μικρότερη από
    MIN_DISTANCE, καταγράφει ένα ενεργό περιστατικό.

    Ο έλεγχος γίνεται με τις τρέχουσες θέσεις της βάσης.
    Δεν χρησιμοποιούμε το ιστορικό προειδοποιήσεων για να
    αποφασίσουμε αν υπάρχει κίνδυνος αυτή τη στιγμή.
    """

    conflicts = []

    # Εξετάζουμε κάθε ζεύγος μία φορά, χωρίς διπλές συγκρίσεις.
    for i in range(len(aircraft)):
        for j in range(i + 1, len(aircraft)):

            plane_a = aircraft[i]
            plane_b = aircraft[j]

            # Υπολογίζουμε τη διαφορά των συντεταγμένων.
            dx = float(plane_a["x"]) - float(plane_b["x"])
            dy = float(plane_a["y"]) - float(plane_b["y"])

            # Ευκλείδεια απόσταση στο δισδιάστατο επίπεδο.
            distance = math.sqrt(dx * dx + dy * dy)

            # Αν η απόσταση είναι μικρότερη από το όριο,
            # θεωρούμε ότι υπάρχει ενεργό περιστατικό.
            if distance < MIN_DISTANCE:
                conflicts.append({
                    "aircraft_id_1": plane_a["aircraft_id"],
                    "aircraft_id_2": plane_b["aircraft_id"],
                    "distance": round(distance, 2)
                })

    return conflicts

# ------------------------------------------------
# 5. API που παρέχει όλα τα δεδομένα στο dashboard
# ------------------------------------------------
@app.route("/api/state")
def api_state():
    """
    Επιστρέφει τα δεδομένα σε μορφή JSON.

    Το JavaScript του browser καλεί αυτή τη διεύθυνση
    κάθε δύο δευτερόλεπτα για να ενημερώνει την οθόνη.
    """

    try:
        # Διαβάζουμε τα πιο πρόσφατα δεδομένα από τη βάση.
        aircraft = get_aircraft_data()
        warnings = get_warning_data()

        # Υπολογίζουμε τον πραγματικό τρέχοντα κίνδυνο
        # από τις θέσεις που διαβάσαμε.
        conflicts = calculate_active_conflicts(aircraft)

        # Το jsonify μετατρέπει το λεξικό Python σε JSON.
        return jsonify({
            "aircraft": aircraft,
            "warnings": warnings,
            "conflicts": conflicts,
            "min_distance": MIN_DISTANCE
        })

    except sqlite3.Error:
        # Αν παρουσιαστεί πρόβλημα με τη βάση, στέλνουμε
        # μήνυμα σφάλματος στον browser με HTTP 500.
        app.logger.exception("Σφάλμα ανάγνωσης της βάσης δεδομένων")

        return jsonify({
            "error": "Δεν ήταν δυνατή η ανάγνωση της βάσης δεδομένων."
        }), 500


# ------------------------------------------------
# 6. Κεντρική σελίδα του dashboard
# ------------------------------------------------
@app.route("/")
def dashboard():

    # Το HTML, το CSS και το JavaScript βρίσκονται εδώ μέσα,
    # ώστε να συνεχίσουμε να χρησιμοποιούμε μόνο το app.py.
    return render_template_string(r"""
<!DOCTYPE html>
<html lang="el">

<head>
    <meta charset="UTF-8">

    <!-- Ο τίτλος της καρτέλας του browser. -->
    <title>AirTrafficSim | Κέντρο Ελέγχου</title>

    <!-- Βελτιώνει την εμφάνιση σε κινητά και μικρές οθόνες. -->
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <style>
        /* ----------------------------------------------------
           ΒΑΣΙΚΕΣ ΡΥΘΜΙΣΕΙΣ ΚΑΙ ΧΡΩΜΑΤΙΚΟ ΘΕΜΑ
           ---------------------------------------------------- */

        :root {
            --background: #080e1a;
            --panel: #101a2b;
            --panel-light: #162338;
            --border: #24334a;
            --text: #e8eef8;
            --muted: #8fa2bd;
            --blue: #55a7ff;
            --green: #35d49a;
            --red: #ff5d73;
            --yellow: #ffc766;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            min-height: 100vh;
            background: var(--background);
            color: var(--text);
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 14px;
        }

        /* Κεντρική στήλη περιεχομένου. */
        .container {
            width: min(1500px, 100%);
            margin: 0 auto;
            padding: 26px;
        }

        /* ----------------------------------------------------
           ΚΕΦΑΛΙΔΑ
           ---------------------------------------------------- */

        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 20px;
            flex-wrap: wrap;
            padding-bottom: 22px;
            border-bottom: 1px solid var(--border);
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 15px;
        }

        .brand-icon {
            display: grid;
            place-items: center;
            width: 54px;
            height: 54px;
            border-radius: 15px;
            background: #172d49;
            border: 1px solid #2d527d;
            font-size: 28px;
        }

        .brand h1 {
            margin: 0;
            font-size: clamp(22px, 3vw, 30px);
            letter-spacing: 1px;
        }

        .brand p {
            margin: 6px 0 0;
            color: var(--muted);
        }

        .connection {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 11px 15px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--panel);
            color: var(--muted);
        }

        .connection-dot {
            width: 9px;
            height: 9px;
            border-radius: 50%;
            background: var(--yellow);
            box-shadow: 0 0 12px currentColor;
        }

        .connection.online .connection-dot {
            background: var(--green);
            color: var(--green);
        }

        .connection.offline .connection-dot {
            background: var(--red);
            color: var(--red);
        }

        /* ----------------------------------------------------
           ΤΙΤΛΟΙ ΕΝΟΤΗΤΩΝ
           ---------------------------------------------------- */

        .section-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 12px;
            margin: 28px 0 15px;
        }

        .section-heading h2 {
            margin: 0;
            font-size: 17px;
        }

        .subheading {
            margin: 6px 0 0;
            color: var(--muted);
            font-size: 12px;
        }

        .eyebrow {
            color: var(--blue);
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.8px;
            text-transform: uppercase;
            margin-bottom: 8px;
        }

        /* ----------------------------------------------------
           ΚΑΡΤΕΣ ΣΤΑΤΙΣΤΙΚΩΝ
           ---------------------------------------------------- */

        .stats {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 15px;
            margin-top: 24px;
        }

        .stat-card {
            position: relative;
            overflow: hidden;
            padding: 20px;
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 14px;
        }

        .stat-card::after {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 2px;
            background: var(--accent, var(--blue));
        }

        .stat-label {
            color: var(--muted);
            font-size: 12px;
        }

        .stat-value {
            margin-top: 12px;
            font-size: 32px;
            font-weight: 700;
            letter-spacing: -1px;
        }

        .stat-note {
            margin-top: 7px;
            color: var(--muted);
            font-size: 11px;
        }

        /* ----------------------------------------------------
           ΚΟΙΝΗ ΕΜΦΑΝΙΣΗ ΤΩΝ ΠΛΑΙΣΙΩΝ
           ---------------------------------------------------- */

        .panel {
            min-width: 0;
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 14px;
            overflow: hidden;
        }

        .panel-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
            padding: 18px 20px;
            border-bottom: 1px solid var(--border);
        }

        .panel-header h2 {
            margin: 0;
            font-size: 15px;
        }

        .panel-body {
            padding: 18px;
        }

        .small-label {
            color: var(--muted);
            font-size: 11px;
        }

        .tag {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 9px;
            border: 1px solid var(--border);
            border-radius: 7px;
            background: var(--panel-light);
            color: var(--muted);
            font-size: 11px;
        }

        /* ----------------------------------------------------
           ΧΑΡΤΗΣ ΕΝΑΕΡΙΟΥ ΧΩΡΟΥ
           ---------------------------------------------------- */

        .map-panel {
            margin-top: 22px;
        }

        .map-wrap {
            width: 100%;
            overflow-x: auto;
            background: #0a1422;
        }

        #airspace-canvas {
            display: block;
            width: 100%;
            height: auto;
            min-width: 540px;
        }

        .map-footer {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 14px;
            padding: 14px 20px;
            border-top: 1px solid var(--border);
        }

        .legend {
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 7px;
            color: var(--muted);
            font-size: 11px;
        }

        .legend-dot {
            width: 9px;
            height: 9px;
            border-radius: 50%;
        }

        /* ----------------------------------------------------
           ΠΙΝΑΚΕΣ
           ---------------------------------------------------- */

        .tables-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.35fr)
                                   minmax(0, 1fr);
            gap: 18px;
            margin-top: 22px;
        }

        .table-wrap {
            width: 100%;
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }

        th {
            padding: 12px 14px;
            background: #142137;
            color: var(--muted);
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.8px;
            text-transform: uppercase;
            white-space: nowrap;
        }

        td {
            padding: 13px 14px;
            border-bottom: 1px solid #1e2b40;
            color: #dce6f5;
            font-size: 12px;
            white-space: nowrap;
        }

        tbody tr:hover {
            background: #15243a;
        }

        tbody tr:last-child td {
            border-bottom: none;
        }

        .plane-id {
            color: var(--blue);
            font-weight: 700;
        }

        .route {
            color: var(--muted);
        }

        .status-pill {
            display: inline-block;
            padding: 6px 9px;
            border-radius: 6px;
            font-size: 10px;
            font-weight: 700;
        }

        .status-safe {
            color: var(--green);
            background: #12372f;
            border: 1px solid #205744;
        }

        .status-danger {
            color: var(--red);
            background: #421d2a;
            border: 1px solid #6b293c;
        }

        .distance-danger {
            color: var(--red);
            font-weight: 700;
        }

        .empty-message {
            padding: 24px;
            text-align: center;
            color: var(--muted);
        }

        /* ----------------------------------------------------
           ΥΠΟΣΕΛΙΔΟ
           ---------------------------------------------------- */

        .footer {
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 24px;
            padding: 18px 0;
            border-top: 1px solid var(--border);
            color: var(--muted);
            font-size: 11px;
        }

        /* ----------------------------------------------------
           ΠΡΟΣΑΡΜΟΓΗ ΓΙΑ ΜΙΚΡΟΤΕΡΕΣ ΟΘΟΝΕΣ
           ---------------------------------------------------- */

        @media (max-width: 950px) {
            .stats {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .tables-grid {
                grid-template-columns: 1fr;
            }
        }

        @media (max-width: 560px) {
            .container {
                padding: 14px;
            }

            .stats {
                gap: 10px;
            }

            .stat-card {
                padding: 15px;
            }

            .stat-value {
                font-size: 26px;
            }

            .brand-icon {
                width: 45px;
                height: 45px;
            }
        }
    </style>
</head>

<body>
<div class="container">

    <!-- Κεντρική κεφαλίδα της εφαρμογής. -->
    <header class="topbar">
        <div class="brand">
            <div class="brand-icon">✈</div>

            <div>
                <div class="eyebrow">Air Traffic Monitoring System</div>
                <h1>AirTrafficSim</h1>
                <p>Κέντρο παρακολούθησης εναέριας κυκλοφορίας</p>
            </div>
        </div>

        <!-- Η JavaScript ενημερώνει αυτή την ένδειξη σύνδεσης. -->
        <div id="connection" class="connection">
            <span class="connection-dot"></span>
            <span id="connection-text">Έλεγχος σύνδεσης...</span>
        </div>
    </header>


    <!-- ------------------------------------------------------
         ΚΑΡΤΕΣ ΣΤΑΤΙΣΤΙΚΩΝ
         ------------------------------------------------------ -->
    <section class="stats">

        <div class="stat-card" style="--accent: #55a7ff;">
            <div class="stat-label">ΣΥΝΟΛΟ ΑΕΡΟΣΚΑΦΩΝ</div>
            <div class="stat-value" id="total-aircraft">—</div>
            <div class="stat-note">Αεροσκάφη στη βάση δεδομένων</div>
        </div>

        <div class="stat-card" style="--accent: #35d49a;">
            <div class="stat-label">ΚΑΝΟΝΙΚΗ ΚΑΤΑΣΤΑΣΗ</div>
            <div class="stat-value" id="safe-aircraft">—</div>
            <div class="stat-note">Χωρίς ενεργή προειδοποίηση</div>
        </div>

        <div class="stat-card" style="--accent: #ff5d73;">
            <div class="stat-label">ΑΕΡΟΣΚΑΦΗ ΣΕ ΚΙΝΔΥΝΟ</div>
            <div class="stat-value" id="danger-aircraft">—</div>
            <div class="stat-note">Με συμμετοχή σε ενεργή σύγκρουση απόστασης</div>
        </div>

        <div class="stat-card" style="--accent: #ffc766;">
            <div class="stat-label">ΕΝΕΡΓΑ ΠΕΡΙΣΤΑΤΙΚΑ</div>
            <div class="stat-value" id="active-conflicts">—</div>
            <div class="stat-note">Ζεύγη κάτω από το όριο απόστασης</div>
        </div>

    </section>


    <!-- ------------------------------------------------------
         ΜΕΓΑΛΟΣ ΔΥΝΑΜΙΚΟΣ ΧΑΡΤΗΣ
         ------------------------------------------------------ -->
    <section class="panel map-panel">

        <div class="panel-header">
            <div>
                <h2>Χάρτης εναέριου χώρου</h2>
                <p class="subheading">
                    Ζωντανή απεικόνιση θέσεων και κατευθύνσεων πτήσης
                </p>
            </div>

            <div class="tag">
                <span style="color: #35d49a;">●</span>
                LIVE MONITORING
            </div>
        </div>

        <div class="map-wrap">
            <canvas id="airspace-canvas"
                    width="1100"
                    height="510">
                Ο browser δεν υποστηρίζει το Canvas.
            </canvas>
        </div>

        <div class="map-footer">
            <div class="legend">
                <div class="legend-item">
                    <span class="legend-dot" style="background:#35d49a;"></span>
                    Κανονική κατάσταση
                </div>

                <div class="legend-item">
                    <span class="legend-dot" style="background:#ff5d73;"></span>
                    Ενεργός κίνδυνος
                </div>

                <div class="legend-item">
                    <span class="legend-dot" style="background:#55a7ff;"></span>
                    Κατεύθυνση κίνησης
                </div>
            </div>

            <div class="small-label">
                Όριο ασφαλείας:
                <strong id="distance-limit">10.0</strong> μονάδες
            </div>
        </div>

    </section>


    <!-- ------------------------------------------------------
         ΠΙΝΑΚΑΣ ΠΤΗΣΕΩΝ ΚΑΙ ΠΡΟΕΙΔΟΠΟΙΗΣΕΩΝ
         ------------------------------------------------------ -->
    <section class="tables-grid">

        <div class="panel">
            <div class="panel-header">
                <div>
                    <h2>Κατάσταση πτήσεων</h2>
                    <p class="subheading">Θέση, ταχύτητα και διαδρομή κάθε αεροσκάφους</p>
                </div>

                <span class="tag" id="flight-count">0 πτήσεις</span>
            </div>

            <div class="table-wrap">
                <table>
                    <thead>
                    <tr>
                            <th>Αεροσκάφος</th>
                            <th>Κατασκευαστής</th>
                            <th>Προέλευση</th>
                            <th>Προορισμός</th>
                            <th>Διαδρομή</th>
                            <th>Θέση X / Y</th>
                            <th>Ταχύτητα</th>
                            <th>Πορεία</th>
                            <th>Κατάσταση</th>
                    </tr>
                    </thead>

                    <tbody id="aircraft-body">
                        <tr>
                            <td colspan="9" class="empty-message">
                                Φόρτωση δεδομένων...
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>


        <div class="panel">
            <div class="panel-header">
                <div>
                    <h2>Ιστορικό προειδοποιήσεων</h2>
                    <p class="subheading">Οι τελευταίες καταχωρίσεις του server</p>
                </div>

                <span class="tag" id="warning-count">0 καταχωρίσεις</span>
            </div>

            <div class="table-wrap">
                <table>
                    <thead>
                    <tr>
                        <th>Ώρα</th>
                        <th>Αεροσκάφη</th>
                        <th>Απόσταση</th>
                    </tr>
                    </thead>

                    <tbody id="warnings-body">
                        <tr>
                            <td colspan="3" class="empty-message">
                                Φόρτωση προειδοποιήσεων...
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

    </section>


    <!-- Υποσέλιδο με πληροφορίες ενημέρωσης. -->
    <footer class="footer">
        <span>AirTrafficSim · Σύστημα προσομοίωσης εναέριας κυκλοφορίας</span>
        <span id="last-update">Τελευταία ενημέρωση: —</span>
    </footer>

</div>


<script>
    // ========================================================
    // JAVASCRIPT — ΔΥΝΑΜΙΚΗ ΛΕΙΤΟΥΡΓΙΑ ΤΟΥ DASHBOARD
    // ========================================================

    // Ανακτούμε το στοιχείο Canvas, όπου σχεδιάζεται ο χάρτης.
    const canvas = document.getElementById("airspace-canvas");

    // Το context 2D περιέχει τις εντολές σχεδίασης.
    const ctx = canvas.getContext("2d");


    // --------------------------------------------------------
    // 1. Σχεδίαση φόντου και πλέγματος του χάρτη
    // --------------------------------------------------------
    function drawGrid() {

        // Καθαρίζουμε την προηγούμενη εικόνα.
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Δημιουργούμε ένα σκούρο φόντο.
        ctx.fillStyle = "#0a1422";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Ρυθμίζουμε τις γραμμές του πλέγματος.
        ctx.strokeStyle = "#1b2b40";
        ctx.lineWidth = 1;

        // Σχεδιάζουμε τις κάθετες γραμμές.
        for (let x = 0; x <= canvas.width; x += 55) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, canvas.height);
            ctx.stroke();
        }

        // Σχεδιάζουμε τις οριζόντιες γραμμές.
        for (let y = 0; y <= canvas.height; y += 55) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(canvas.width, y);
            ctx.stroke();
        }

        // Προσθέτουμε διακριτικές ετικέτες στους άξονες.
        ctx.fillStyle = "#8295af";
        ctx.font = "12px Segoe UI, Arial";
        ctx.fillText("X →", canvas.width - 42, canvas.height - 12);
        ctx.fillText("Y ↑", 12, 18);
    }


    // --------------------------------------------------------
    // 2. Δημιουργία συνόλου με τα αεροσκάφη σε ενεργό κίνδυνο
    // --------------------------------------------------------
    function getDangerousAircraft(conflicts) {

        // Το Set κρατά κάθε ID μόνο μία φορά, ακόμη κι αν
        // το ίδιο αεροσκάφος συμμετέχει σε πολλά περιστατικά.
        const dangerous = new Set();

        for (const conflict of conflicts) {
            dangerous.add(conflict.aircraft_id_1);
            dangerous.add(conflict.aircraft_id_2);
        }

        return dangerous;
    }


    // --------------------------------------------------------
    // 3. Σχεδίαση συμβόλου αεροσκάφους
    // --------------------------------------------------------
    function drawPlane(px, py, heading, color) {

        // Αποθηκεύουμε τις ρυθμίσεις σχεδίασης πριν από
        // την περιστροφή, ώστε να μην επηρεαστούν άλλα στοιχεία.
        ctx.save();

        // Μεταφέρουμε το σημείο σχεδίασης στη θέση του αεροσκάφους.
        ctx.translate(px, py);

        // Το heading είναι σε μοίρες, ενώ το Canvas
        // απαιτεί γωνία σε ακτίνια.
        const angle = Number(heading) * Math.PI / 180;

        // Περιστρέφουμε το αεροσκάφος σύμφωνα με την πορεία.
        ctx.rotate(angle);

        // Σχηματίζουμε ένα απλό σύμβολο αεροσκάφους.
        // Η μύτη του αρχικού σχήματος δείχνει προς τα πάνω.
        ctx.beginPath();
        ctx.moveTo(0, -13);
        ctx.lineTo(3, -3);
        ctx.lineTo(12, 4);
        ctx.lineTo(12, 7);
        ctx.lineTo(3, 5);
        ctx.lineTo(3, 11);
        ctx.lineTo(7, 14);
        ctx.lineTo(7, 16);
        ctx.lineTo(0, 14);
        ctx.lineTo(-7, 16);
        ctx.lineTo(-7, 14);
        ctx.lineTo(-3, 11);
        ctx.lineTo(-3, 5);
        ctx.lineTo(-12, 7);
        ctx.lineTo(-12, 4);
        ctx.lineTo(-3, -3);
        ctx.closePath();

        // Χρωματίζουμε το αεροσκάφος ανάλογα με την κατάστασή του.
        ctx.fillStyle = color;
        ctx.fill();

        // Προσθέτουμε λεπτό περίγραμμα για καλύτερη αντίθεση.
        ctx.strokeStyle = "#f8fafc";
        ctx.lineWidth = 1;
        ctx.stroke();

        // Επαναφέρουμε τις αρχικές ρυθμίσεις του Canvas.
        ctx.restore();
    }


    // --------------------------------------------------------
    // 4. Σχεδίαση όλων των αεροσκαφών στον χάρτη
    // --------------------------------------------------------
    function drawAircraft(aircraft, conflicts) {

        // Ξεκινάμε με καθαρό πλέγμα.
        drawGrid();

        // Δημιουργούμε το σύνολο των αεροσκαφών που κινδυνεύουν.
        const dangerous = getDangerousAircraft(conflicts);

        // Υπολογίζουμε τα όρια των θέσεων για δυναμική κλίμακα.
        const xs = aircraft.map(p => Number(p.x));
        const ys = aircraft.map(p => Number(p.y));

        // Εξασφαλίζουμε ότι ο χάρτης καλύπτει τουλάχιστον
        // το εύρος 0 έως 100, ακόμη κι αν όλα τα αεροσκάφη
        // βρίσκονται σε μικρότερη περιοχή.
        const minX = Math.min(0, ...xs);
        const maxX = Math.max(100, ...xs);
        const minY = Math.min(0, ...ys);
        const maxY = Math.max(100, ...ys);

        // Αφήνουμε περιθώριο στα άκρα για να μη βγαίνουν
        // τα σύμβολα έξω από τον χάρτη.
        const padding = 35;

        const usableWidth = canvas.width - 2 * padding;
        const usableHeight = canvas.height - 2 * padding;

        const scaleX = usableWidth / Math.max(1, maxX - minX);
        const scaleY = usableHeight / Math.max(1, maxY - minY);

        // Σχεδιάζουμε κάθε αεροσκάφος.
        for (const plane of aircraft) {

            // Μετατροπή της συντεταγμένης X σε εικονοστοιχεία.
            const px = padding + (Number(plane.x) - minX) * scaleX;

            // Ο άξονας Y του Canvas αυξάνεται προς τα κάτω,
            // οπότε αντιστρέφουμε την κατακόρυφη συντεταγμένη.
            const py = canvas.height - padding -
                      (Number(plane.y) - minY) * scaleY;

            // Ελέγχουμε αν το αεροσκάφος συμμετέχει σε
            // περιστατικό μικρής απόστασης αυτή τη στιγμή.
            const isDangerous = dangerous.has(plane.aircraft_id);

            // Κόκκινο για ενεργό κίνδυνο, πράσινο διαφορετικά.
            const color = isDangerous ? "#ff5d73" : "#35d49a";

            // Σχεδιάζουμε τη γραμμή που υποδεικνύει την κατεύθυνση.
            const angle = Number(plane.heading) * Math.PI / 180;
            const lineLength = 30;

            ctx.beginPath();
            ctx.moveTo(px, py);
            ctx.lineTo(
                px + Math.sin(angle) * lineLength,
                py - Math.cos(angle) * lineLength
            );

            ctx.strokeStyle = "#55a7ff";
            ctx.lineWidth = 2;
            ctx.stroke();

            // Προσθέτουμε μια διακριτική κυκλική ένδειξη
            // γύρω από τη θέση του αεροσκάφους.
            ctx.beginPath();
            ctx.arc(px, py, 19, 0, 2 * Math.PI);
            ctx.strokeStyle = isDangerous
                ? "rgba(255, 93, 115, 0.45)"
                : "rgba(53, 212, 154, 0.25)";
            ctx.lineWidth = 1.5;
            ctx.stroke();

            // Σχεδιάζουμε το σύμβολο του αεροσκάφους.
            drawPlane(px, py, plane.heading, color);

            // Γράφουμε το αναγνωριστικό δίπλα στο σύμβολο.
            ctx.fillStyle = "#e8eef8";
            ctx.font = "bold 12px Segoe UI, Arial";
            ctx.fillText(plane.aircraft_id, px + 20, py - 15);

            // Όταν υπάρχει κίνδυνος, προσθέτουμε σχετική ένδειξη.
            if (isDangerous) {
                ctx.fillStyle = "#ff8494";
                ctx.font = "bold 10px Segoe UI, Arial";
                ctx.fillText("WARNING", px + 20, py - 2);
            }
        }
    }


    // --------------------------------------------------------
    // 5. Ενημέρωση των καρτών στατιστικών
    // --------------------------------------------------------
    function updateStatistics(aircraft, conflicts) {

        // Συγκεντρώνουμε τα IDs όλων των αεροσκαφών
        // που συμμετέχουν σε ενεργά περιστατικά.
        const dangerous = getDangerousAircraft(conflicts);

        // Συνολικός αριθμός αεροσκαφών.
        document.getElementById("total-aircraft").textContent =
            aircraft.length;

        // Αριθμός αεροσκαφών χωρίς ενεργό περιστατικό.
        document.getElementById("safe-aircraft").textContent =
            aircraft.length - dangerous.size;

        // Αριθμός διαφορετικών αεροσκαφών που βρίσκονται σε κίνδυνο.
        document.getElementById("danger-aircraft").textContent =
            dangerous.size;

        // Αριθμός ζευγών που βρίσκονται κάτω από το όριο απόστασης.
        document.getElementById("active-conflicts").textContent =
            conflicts.length;

        // Εμφανίζουμε και το όριο ασφαλείας που χρησιμοποιεί
        // η εφαρμογή στον υπολογισμό των αποστάσεων.
        document.getElementById("distance-limit").textContent =
            Number(MIN_DISTANCE_JS).toFixed(1);
    }


    // --------------------------------------------------------
    // 6. Ενημέρωση πίνακα πτήσεων
    // --------------------------------------------------------
    function updateAircraftTable(aircraft, conflicts) {

        const tbody = document.getElementById("aircraft-body");

        // Αφαιρούμε τις παλιές γραμμές.
        tbody.replaceChildren();

        // Εντοπίζουμε τα αεροσκάφη που συμμετέχουν σε κίνδυνο.
        const dangerous = getDangerousAircraft(conflicts);

        // Ενημερώνουμε τον αριθμό των εμφανιζόμενων πτήσεων.
        document.getElementById("flight-count").textContent =
            aircraft.length + " πτήσεις";

        // Εμφανίζουμε μήνυμα όταν η βάση δεν περιέχει αεροσκάφη.
        if (aircraft.length === 0) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");

            cell.colSpan = 9;
            cell.className = "empty-message";
            cell.textContent = "Δεν υπάρχουν καταχωρισμένα αεροσκάφη.";

            row.appendChild(cell);
            tbody.appendChild(row);
            return;
        }

        for (const plane of aircraft) {

            const isDangerous = dangerous.has(plane.aircraft_id);
            const row = document.createElement("tr");

            // Δημιουργούμε τα κελιά της γραμμής.
            // Οι συντεταγμένες εμφανίζονται με δύο δεκαδικά ψηφία.
            
            const values = [
                plane.aircraft_id,
                plane.manufacturer || "—",
                plane.origin || "—",
                plane.destination || "—",
                String(plane.origin || "—") + " → " +
                    String(plane.destination || "—"),
                Number(plane.x).toFixed(2) + " / " +
                    Number(plane.y).toFixed(2),
                Number(plane.speed).toFixed(2),
                Number(plane.heading).toFixed(0) + "°"
            ];


            for (let i = 0; i < values.length; i++) {
                const cell = document.createElement("td");

                // Χρησιμοποιούμε textContent ώστε οι τιμές
                // να εμφανίζονται ως κείμενο και όχι ως HTML.
                cell.textContent = values[i];

                // Ξεχωρίζουμε οπτικά το αναγνωριστικό.
                if (i === 0) {
                    cell.className = "plane-id";
                }

                // Ξεχωρίζουμε τη διαδρομή από τα αριθμητικά δεδομένα.
                if (i === 4) {
                    cell.className = "route";
                }

                row.appendChild(cell);
            }

            // Δημιουργούμε το κελί της κατάστασης.
            const statusCell = document.createElement("td");
            const pill = document.createElement("span");

            pill.className = isDangerous
                ? "status-pill status-danger"
                : "status-pill status-safe";

            pill.textContent = isDangerous
                ? "⚠ ΚΙΝΔΥΝΟΣ"
                : "✓ ΚΑΝΟΝΙΚΟ";

            statusCell.appendChild(pill);
            row.appendChild(statusCell);

            tbody.appendChild(row);
        }
    }


    // --------------------------------------------------------
    // 7. Ενημέρωση ιστορικού προειδοποιήσεων
    // --------------------------------------------------------
    function updateWarningsTable(warnings) {

        const tbody = document.getElementById("warnings-body");

        // Αδειάζουμε τον πίνακα πριν προσθέσουμε τις νέες εγγραφές.
        tbody.replaceChildren();

        // Ενημερώνουμε το πλήθος των προειδοποιήσεων που εμφανίζονται.
        document.getElementById("warning-count").textContent =
            warnings.length + " καταχωρίσεις";

        // Εμφανίζουμε σχετικό μήνυμα όταν δεν υπάρχουν προειδοποιήσεις.
        if (warnings.length === 0) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");

            cell.colSpan = 3;
            cell.className = "empty-message";
            cell.textContent = "Δεν υπάρχουν καταγεγραμμένες προειδοποιήσεις.";

            row.appendChild(cell);
            tbody.appendChild(row);
            return;
        }

        for (const warning of warnings) {

            const row = document.createElement("tr");

            // Παίρνουμε μόνο την ώρα για πιο συμπαγή εμφάνιση.
            const timestamp = String(warning.timestamp || "—");
            const time = timestamp.length >= 19
                ? timestamp.substring(11, 19)
                : timestamp;

            // Δημιουργούμε τρία κελιά: ώρα, ζεύγος, απόσταση.
            const timeCell = document.createElement("td");
            timeCell.textContent = time;
            timeCell.className = "route";
            row.appendChild(timeCell);

            const pairCell = document.createElement("td");
            pairCell.textContent =
                warning.aircraft_id_1 + " / " + warning.aircraft_id_2;
            pairCell.className = "plane-id";
            row.appendChild(pairCell);

            const distanceCell = document.createElement("td");
            distanceCell.textContent =
                Number(warning.distance).toFixed(2);
            distanceCell.className = "distance-danger";
            row.appendChild(distanceCell);

            tbody.appendChild(row);
        }
    }


    // --------------------------------------------------------
    // 8. Ενημέρωση ένδειξης σύνδεσης
    // --------------------------------------------------------
    function setConnectionStatus(isOnline, message) {

        const connection = document.getElementById("connection");
        const connectionText = document.getElementById("connection-text");

        // Αλλάζουμε την κλάση CSS για να αλλάξει το χρώμα
        // της ένδειξης σύνδεσης.
        connection.classList.toggle("online", isOnline);
        connection.classList.toggle("offline", !isOnline);

        connectionText.textContent = message;
    }


    // --------------------------------------------------------
    // 9. Κύρια συνάρτηση ανανέωσης
    // --------------------------------------------------------
    async function refreshDashboard() {

        try {

            // Ζητάμε από το Flask τα πιο πρόσφατα δεδομένα.
            const response = await fetch("/api/state", {
                cache: "no-store"
            });

            // Αν ο server επέστρεψε σφάλμα, σταματάμε την ενημέρωση.
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }

            // Μετατρέπουμε το JSON σε αντικείμενο JavaScript.
            const data = await response.json();

            // Αν το API έστειλε μήνυμα σφάλματος, το εμφανίζουμε.
            if (data.error) {
                throw new Error(data.error);
            }

            // Αποθηκεύουμε το όριο που χρησιμοποιεί ο server
            // ώστε να εμφανίζεται σωστά στις κάρτες στατιστικών.
            MIN_DISTANCE_JS = Number(data.min_distance);

            // Ανανεώνουμε όλα τα στοιχεία της σελίδας.
            drawAircraft(data.aircraft, data.conflicts);

            updateStatistics(data.aircraft, data.conflicts);

            updateAircraftTable(data.aircraft, data.conflicts);

            updateWarningsTable(data.warnings);

            // Δηλώνουμε ότι η σύνδεση με το API λειτουργεί.
            setConnectionStatus(true, "Σύνδεση ενεργή");

            // Εμφανίζουμε την τοπική ώρα τελευταίας ενημέρωσης.
            document.getElementById("last-update").textContent =
                "Τελευταία ενημέρωση: " +
                new Date().toLocaleTimeString("el-GR");

        } catch (error) {

            // Αν αποτύχει η σύνδεση ή η ανάγνωση δεδομένων,
            // εμφανίζουμε καθαρό μήνυμα στην κεφαλίδα.
            setConnectionStatus(false, "Σφάλμα σύνδεσης");

            console.error("Σφάλμα ανανέωσης dashboard:", error);
        }
    }


    // --------------------------------------------------------
    // 10. Έναρξη της αυτόματης ανανέωσης
    // --------------------------------------------------------

    // Αρχική τιμή του ορίου ασφαλείας. Θα αντικατασταθεί
    // από την τιμή που επιστρέφει ο server στο πρώτο API call.
    let MIN_DISTANCE_JS = 10.0;

    // Κάνουμε μία ανανέωση αμέσως με το άνοιγμα της σελίδας.
    refreshDashboard();

    // Επαναλαμβάνουμε την ανανέωση ανά δύο δευτερόλεπτα.
    setInterval(refreshDashboard, 2000);

</script>

</body>
</html>
""")


# ------------------------------------------------
# 7. Εκκίνηση του τοπικού web server
# ------------------------------------------------
if __name__ == "__main__":

    # Ακούμε μόνο στον τοπικό υπολογιστή.
    # Η ρύθμιση αυτή δεν εκθέτει το dashboard στο δίκτυο.
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=True
    )
