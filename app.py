# ================================================================
# app.py
# AirTrafficSim - Air Traffic Control Dashboard
# ================================================================
# What this application provides:
# 1. A modern air traffic control dashboard.
# 2. Aircraft positions read from the SQLite database.
# 3. A dynamic two-dimensional airspace map.
# 4. Live distance calculation between aircraft.
# 5. Red highlighting of aircraft currently in danger.
# 6. Statistics, flight details and warning history.
# 7. Automatic refresh every two seconds.
#
# Note:
# This app reuses dataBase.py and airtraffic.db. It does not
# replace the UDP server or the aircraft simulation.
# ================================================================

import math
import sqlite3

from flask import Flask, render_template_string, jsonify

# Reuse the shared data access functions from dataBase.py.
from dataBase import get_all_aircraft, get_recent_warnings


# ------------------------------------------------
# 1. Application settings
# ------------------------------------------------

# Create the Flask application.
app = Flask(__name__)

# Minimum allowed distance in model units.
# Must match MIN_DISTANCE in server.py.
MIN_DISTANCE = 10.0

# Automatic refresh interval in milliseconds.
REFRESH_INTERVAL = 2000


# ------------------------------------------------
# 2. Read aircraft data from SQLite
# ------------------------------------------------
def get_aircraft_data():
    """
    Read all aircraft from the database.

    Returns a list of dicts so the data can be easily
    converted to JSON for the dashboard.
    """

    # The shared data layer reuses one connection per thread.
    return get_all_aircraft()


# ------------------------------------------------
# 3. Read warning history from SQLite
# ------------------------------------------------
def get_warning_data():
    """
    Read the 20 most recent warnings stored by the server.
    """

    return get_recent_warnings(20)


# ------------------------------------------------
# 4. Compute current distances between aircraft
# ------------------------------------------------
def calculate_active_conflicts(aircraft):
    """
    Check every possible pair of aircraft.

    If the distance between two aircraft is below MIN_DISTANCE,
    an active conflict is recorded.

    The check uses the current positions from the database.
    The warning history is not used to decide whether a
    conflict is active right now.
    """

    conflicts = []

    # Examine each pair once, without duplicate comparisons.
    for i in range(len(aircraft)):
        for j in range(i + 1, len(aircraft)):

            plane_a = aircraft[i]
            plane_b = aircraft[j]

            # Coordinate differences.
            dx = float(plane_a["x"]) - float(plane_b["x"])
            dy = float(plane_a["y"]) - float(plane_b["y"])

            # Euclidean distance in the plane.
            distance = math.sqrt(dx * dx + dy * dy)

            # Below the limit means an active conflict.
            if distance < MIN_DISTANCE:
                conflicts.append({
                    "aircraft_id_1": plane_a["aircraft_id"],
                    "aircraft_id_2": plane_b["aircraft_id"],
                    "distance": round(distance, 2)
                })

    return conflicts


# ------------------------------------------------
# 5. API providing all data to the dashboard
# ------------------------------------------------
@app.route("/api/state")
def api_state():
    """
    Return the dashboard data as JSON.

    The browser JavaScript calls this endpoint every two
    seconds to refresh the screen.
    """

    try:
        # Read the latest data from the database.
        aircraft = get_aircraft_data()
        warnings = get_warning_data()

        # Compute the real current danger from the positions.
        conflicts = calculate_active_conflicts(aircraft)

        # jsonify converts the Python dict to a JSON response.
        return jsonify({
            "aircraft": aircraft,
            "warnings": warnings,
            "conflicts": conflicts,
            "min_distance": MIN_DISTANCE
        })

    except sqlite3.Error:
        # On a database problem, return an HTTP 500 error message.
        app.logger.exception("Error reading the database")

        return jsonify({
            "error": "The database could not be read."
        }), 500


# ------------------------------------------------
# 6. Main dashboard page
# ------------------------------------------------
@app.route("/")
def dashboard():

    # The HTML, CSS and JavaScript are embedded here so the
    # whole dashboard lives in a single Python file.
    return render_template_string(r"""
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">

    <!-- Browser tab title. -->
    <title>AirTrafficSim | Control Center</title>

    <!-- Improves rendering on phones and small screens. -->
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <style>
        /* ----------------------------------------------------
           BASE SETTINGS AND COLOR THEME
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

        /* Central content column. */
        .container {
            width: min(1500px, 100%);
            margin: 0 auto;
            padding: 26px;
        }

        /* ----------------------------------------------------
           HEADER
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
           SECTION HEADINGS
           ---------------------------------------------------- */

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
           STATISTICS CARDS
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

        /* Colored accent line at the top of each card. */
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
           COMMON PANEL STYLE
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
           AIRSPACE MAP
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
           TABLES
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
           FOOTER
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
           RESPONSIVE LAYOUT FOR SMALLER SCREENS
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
        }
    </style>
</head>

<body>
<div class="container">

    <!-- Main application header. -->
    <header class="topbar">
        <div class="brand">
            <div class="eyebrow">Air Traffic Monitoring System</div>
            <h1>AirTrafficSim</h1>
            <p>Air traffic monitoring center</p>
        </div>

        <!-- The JavaScript updates this connection indicator. -->
        <div id="connection" class="connection">
            <span class="connection-dot"></span>
            <span id="connection-text">Checking connection...</span>
        </div>
    </header>


    <!-- ------------------------------------------------------
         STATISTICS CARDS
         ------------------------------------------------------ -->
    <section class="stats">

        <div class="stat-card" style="--accent: #55a7ff;">
            <div class="stat-label">TOTAL AIRCRAFT</div>
            <div class="stat-value" id="total-aircraft">-</div>
            <div class="stat-note">Aircraft in the database</div>
        </div>

        <div class="stat-card" style="--accent: #35d49a;">
            <div class="stat-label">NORMAL STATUS</div>
            <div class="stat-value" id="safe-aircraft">-</div>
            <div class="stat-note">No active warning</div>
        </div>

        <div class="stat-card" style="--accent: #ff5d73;">
            <div class="stat-label">AIRCRAFT IN DANGER</div>
            <div class="stat-value" id="danger-aircraft">-</div>
            <div class="stat-note">Involved in an active separation conflict</div>
        </div>

        <div class="stat-card" style="--accent: #ffc766;">
            <div class="stat-label">ACTIVE CONFLICTS</div>
            <div class="stat-value" id="active-conflicts">-</div>
            <div class="stat-note">Pairs below the distance limit</div>
        </div>

    </section>


    <!-- ------------------------------------------------------
         LARGE DYNAMIC MAP
         ------------------------------------------------------ -->
    <section class="panel map-panel">

        <div class="panel-header">
            <div>
                <h2>Airspace map</h2>
                <p class="subheading">
                    Live view of aircraft positions and headings
                </p>
            </div>

            <div class="tag">
                <span style="color: #35d49a;">&#9679;</span>
                LIVE MONITORING
            </div>
        </div>

        <div class="map-wrap">
            <canvas id="airspace-canvas"
                    width="1100"
                    height="510">
                Your browser does not support the Canvas element.
            </canvas>
        </div>

        <div class="map-footer">
            <div class="legend">
                <div class="legend-item">
                    <span class="legend-dot" style="background:#35d49a;"></span>
                    Normal status
                </div>

                <div class="legend-item">
                    <span class="legend-dot" style="background:#ff5d73;"></span>
                    Active danger
                </div>

                <div class="legend-item">
                    <span class="legend-dot" style="background:#55a7ff;"></span>
                    Direction of movement
                </div>
            </div>

            <div class="small-label">
                Safety limit:
                <strong id="distance-limit">10.0</strong> units
            </div>
        </div>

    </section>


    <!-- ------------------------------------------------------
         FLIGHT TABLE AND WARNING HISTORY
         ------------------------------------------------------ -->
    <section class="tables-grid">

        <div class="panel">
            <div class="panel-header">
                <div>
                    <h2>Flight status</h2>
                    <p class="subheading">Position, speed and route of each aircraft</p>
                </div>

                <span class="tag" id="flight-count">0 flights</span>
            </div>

            <div class="table-wrap">
                <table>
                    <thead>
                    <tr>
                        <th>Aircraft</th>
                        <th>Manufacturer</th>
                        <th>Origin</th>
                        <th>Destination</th>
                        <th>Route</th>
                        <th>Position X / Y</th>
                        <th>Speed</th>
                        <th>Heading</th>
                        <th>Status</th>
                    </tr>
                    </thead>

                    <tbody id="aircraft-body">
                        <tr>
                            <td colspan="9" class="empty-message">
                                Loading data...
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>


        <div class="panel">
            <div class="panel-header">
                <div>
                    <h2>Warning history</h2>
                    <p class="subheading">Latest entries recorded by the server</p>
                </div>

                <span class="tag" id="warning-count">0 entries</span>
            </div>

            <div class="table-wrap">
                <table>
                    <thead>
                    <tr>
                        <th>Time</th>
                        <th>Aircraft</th>
                        <th>Distance</th>
                    </tr>
                    </thead>

                    <tbody id="warnings-body">
                        <tr>
                            <td colspan="3" class="empty-message">
                                Loading warnings...
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

    </section>


    <!-- Footer with update information. -->
    <footer class="footer">
        <span>AirTrafficSim - Air traffic simulation system</span>
        <span id="last-update">Last update: -</span>
    </footer>

</div>


<script>
    // ========================================================
    // JAVASCRIPT - DASHBOARD BEHAVIOR
    // ========================================================

    // Get the canvas element on which the map is drawn.
    const canvas = document.getElementById("airspace-canvas");

    // The 2D context provides the drawing commands.
    const ctx = canvas.getContext("2d");


    // --------------------------------------------------------
    // 1. Draw the map background and grid
    // --------------------------------------------------------
    function drawGrid() {

        // Clear the previous frame.
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Fill the dark background.
        ctx.fillStyle = "#0a1422";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Configure the grid lines.
        ctx.strokeStyle = "#1b2b40";
        ctx.lineWidth = 1;

        // Draw the vertical lines.
        for (let x = 0; x <= canvas.width; x += 55) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, canvas.height);
            ctx.stroke();
        }

        // Draw the horizontal lines.
        for (let y = 0; y <= canvas.height; y += 55) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(canvas.width, y);
            ctx.stroke();
        }

        // Add subtle axis labels.
        ctx.fillStyle = "#8295af";
        ctx.font = "12px Segoe UI, Arial";
        ctx.fillText("X >", canvas.width - 42, canvas.height - 12);
        ctx.fillText("Y ^", 12, 18);
    }


    // --------------------------------------------------------
    // 2. Build the set of aircraft currently in danger
    // --------------------------------------------------------
    function getDangerousAircraft(conflicts) {

        // A Set stores each ID only once, even if the same
        // aircraft is part of several conflicts.
        const dangerous = new Set();

        for (const conflict of conflicts) {
            dangerous.add(conflict.aircraft_id_1);
            dangerous.add(conflict.aircraft_id_2);
        }

        return dangerous;
    }


    // --------------------------------------------------------
    // 3. Draw an aircraft symbol
    // --------------------------------------------------------
    function drawPlane(px, py, heading, color) {

        // Save the drawing state before rotating, so other
        // elements are not affected.
        ctx.save();

        // Move the drawing origin to the aircraft position.
        ctx.translate(px, py);

        // The heading is in degrees, while the canvas expects radians.
        const angle = Number(heading) * Math.PI / 180;

        // Rotate the symbol according to the heading.
        ctx.rotate(angle);

        // Draw a simple aircraft shape.
        // The nose of the original shape points upwards.
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

        // Fill the aircraft according to its status.
        ctx.fillStyle = color;
        ctx.fill();

        // Add a thin outline for better contrast.
        ctx.strokeStyle = "#f8fafc";
        ctx.lineWidth = 1;
        ctx.stroke();

        // Restore the original canvas state.
        ctx.restore();
    }


    // --------------------------------------------------------
    // 4. Draw all aircraft on the map
    // --------------------------------------------------------
    function drawAircraft(aircraft, conflicts) {

        // Start from a clean grid.
        drawGrid();

        // Set of aircraft currently in danger.
        const dangerous = getDangerousAircraft(conflicts);

        // Compute position bounds for a dynamic scale.
        const xs = aircraft.map(p => Number(p.x));
        const ys = aircraft.map(p => Number(p.y));

        // Make sure the map covers at least the range 0 to 100,
        // even if all aircraft are inside a smaller area.
        const minX = Math.min(0, ...xs);
        const maxX = Math.max(100, ...xs);
        const minY = Math.min(0, ...ys);
        const maxY = Math.max(100, ...ys);

        // Margin around the edges so symbols stay on the map.
        const padding = 35;

        const usableWidth = canvas.width - 2 * padding;
        const usableHeight = canvas.height - 2 * padding;

        const scaleX = usableWidth / Math.max(1, maxX - minX);
        const scaleY = usableHeight / Math.max(1, maxY - minY);

        // Draw each aircraft.
        for (const plane of aircraft) {

            // Convert the X coordinate to pixels.
            const px = padding + (Number(plane.x) - minX) * scaleX;

            // The canvas Y axis grows downwards, so the vertical
            // coordinate is inverted.
            const py = canvas.height - padding -
                      (Number(plane.y) - minY) * scaleY;

            // Is this aircraft part of a conflict right now?
            const isDangerous = dangerous.has(plane.aircraft_id);

            // Red for active danger, green otherwise.
            const color = isDangerous ? "#ff5d73" : "#35d49a";

            // Draw the line that indicates the direction of movement.
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

            // Draw a subtle circle around the aircraft position.
            ctx.beginPath();
            ctx.arc(px, py, 19, 0, 2 * Math.PI);
            ctx.strokeStyle = isDangerous
                ? "rgba(255, 93, 115, 0.45)"
                : "rgba(53, 212, 154, 0.25)";
            ctx.lineWidth = 1.5;
            ctx.stroke();

            // Draw the aircraft symbol.
            drawPlane(px, py, plane.heading, color);

            // Write the identifier next to the symbol.
            ctx.fillStyle = "#e8eef8";
            ctx.font = "bold 12px Segoe UI, Arial";
            ctx.fillText(plane.aircraft_id, px + 20, py - 15);

            // Add a warning label when the aircraft is in danger.
            if (isDangerous) {
                ctx.fillStyle = "#ff8494";
                ctx.font = "bold 10px Segoe UI, Arial";
                ctx.fillText("WARNING", px + 20, py - 2);
            }
        }
    }


    // --------------------------------------------------------
    // 5. Update the statistics cards
    // --------------------------------------------------------
    function updateStatistics(aircraft, conflicts) {

        // IDs of all aircraft involved in active conflicts.
        const dangerous = getDangerousAircraft(conflicts);

        // Total number of aircraft.
        document.getElementById("total-aircraft").textContent =
            aircraft.length;

        // Aircraft without an active conflict.
        document.getElementById("safe-aircraft").textContent =
            aircraft.length - dangerous.size;

        // Number of distinct aircraft in danger.
        document.getElementById("danger-aircraft").textContent =
            dangerous.size;

        // Number of pairs below the distance limit.
        document.getElementById("active-conflicts").textContent =
            conflicts.length;

        // Show the safety limit used for the distance calculation.
        document.getElementById("distance-limit").textContent =
            Number(MIN_DISTANCE_JS).toFixed(1);
    }


    // --------------------------------------------------------
    // 6. Update the flight table
    // --------------------------------------------------------
    function updateAircraftTable(aircraft, conflicts) {

        const tbody = document.getElementById("aircraft-body");

        // Remove the old rows.
        tbody.replaceChildren();

        // Aircraft currently involved in a conflict.
        const dangerous = getDangerousAircraft(conflicts);

        // Update the displayed flight count.
        document.getElementById("flight-count").textContent =
            aircraft.length + " flights";

        // Show a message when the database has no aircraft.
        if (aircraft.length === 0) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");

            cell.colSpan = 9;
            cell.className = "empty-message";
            cell.textContent = "No aircraft are registered.";

            row.appendChild(cell);
            tbody.appendChild(row);
            return;
        }

        for (const plane of aircraft) {

            const isDangerous = dangerous.has(plane.aircraft_id);
            const row = document.createElement("tr");

            // Values of the row cells.
            // Coordinates are shown with two decimal places.
            const values = [
                plane.aircraft_id,
                plane.manufacturer || "-",
                plane.origin || "-",
                plane.destination || "-",
                String(plane.origin || "-") + " > " +
                    String(plane.destination || "-"),
                Number(plane.x).toFixed(2) + " / " +
                    Number(plane.y).toFixed(2),
                Number(plane.speed).toFixed(2),
                Number(plane.heading).toFixed(0) + "\u00B0"
            ];

            for (let i = 0; i < values.length; i++) {
                const cell = document.createElement("td");

                // Use textContent so values are displayed as
                // plain text and never interpreted as HTML.
                cell.textContent = values[i];

                // Visually distinguish the identifier.
                if (i === 0) {
                    cell.className = "plane-id";
                }

                // Distinguish the route from the numeric data.
                if (i === 4) {
                    cell.className = "route";
                }

                row.appendChild(cell);
            }

            // Build the status cell.
            const statusCell = document.createElement("td");
            const pill = document.createElement("span");

            pill.className = isDangerous
                ? "status-pill status-danger"
                : "status-pill status-safe";

            pill.textContent = isDangerous ? "DANGER" : "NORMAL";

            statusCell.appendChild(pill);
            row.appendChild(statusCell);

            tbody.appendChild(row);
        }
    }


    // --------------------------------------------------------
    // 7. Update the warning history table
    // --------------------------------------------------------
    function updateWarningsTable(warnings) {

        const tbody = document.getElementById("warnings-body");

        // Empty the table before adding the new entries.
        tbody.replaceChildren();

        // Update the number of displayed warnings.
        document.getElementById("warning-count").textContent =
            warnings.length + " entries";

        // Show a message when there are no warnings.
        if (warnings.length === 0) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");

            cell.colSpan = 3;
            cell.className = "empty-message";
            cell.textContent = "No warnings have been recorded.";

            row.appendChild(cell);
            tbody.appendChild(row);
            return;
        }

        for (const warning of warnings) {

            const row = document.createElement("tr");

            // Keep only the time part for a more compact display.
            const timestamp = String(warning.timestamp || "-");
            const time = timestamp.length >= 19
                ? timestamp.substring(11, 19)
                : timestamp;

            // Three cells: time, aircraft pair, distance.
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
    // 8. Update the connection indicator
    // --------------------------------------------------------
    function setConnectionStatus(isOnline, message) {

        const connection = document.getElementById("connection");
        const connectionText = document.getElementById("connection-text");

        // Toggle the CSS classes that control the indicator color.
        connection.classList.toggle("online", isOnline);
        connection.classList.toggle("offline", !isOnline);

        connectionText.textContent = message;
    }


    // --------------------------------------------------------
    // 9. Main refresh function
    // --------------------------------------------------------
    async function refreshDashboard() {

        try {

            // Ask Flask for the latest data.
            const response = await fetch("/api/state", {
                cache: "no-store"
            });

            // If the server returned an error, stop the update.
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }

            // Convert the JSON response to a JavaScript object.
            const data = await response.json();

            // If the API reported an error, surface it.
            if (data.error) {
                throw new Error(data.error);
            }

            // Store the limit used by the server so it is shown
            // correctly in the statistics cards.
            MIN_DISTANCE_JS = Number(data.min_distance);

            // Refresh every element of the page.
            drawAircraft(data.aircraft, data.conflicts);

            updateStatistics(data.aircraft, data.conflicts);

            updateAircraftTable(data.aircraft, data.conflicts);

            updateWarningsTable(data.warnings);

            // Report that the API connection is working.
            setConnectionStatus(true, "Connection active");

            // Show the local time of the last update.
            document.getElementById("last-update").textContent =
                "Last update: " +
                new Date().toLocaleTimeString("en-GB");

        } catch (error) {

            // If the connection or data read fails, show a
            // clear message in the header.
            setConnectionStatus(false, "Connection error");

            console.error("Dashboard refresh error:", error);
        }
    }


    // --------------------------------------------------------
    // 10. Start the automatic refresh
    // --------------------------------------------------------

    // Initial value of the safety limit. It is replaced by the
    // value returned by the server on the first API call.
    let MIN_DISTANCE_JS = 10.0;

    // Refresh once immediately when the page opens.
    refreshDashboard();

    // Repeat the refresh every two seconds.
    setInterval(refreshDashboard, 2000);

</script>

</body>
</html>
""")


# ------------------------------------------------
# 7. Start the local web server
# ------------------------------------------------
if __name__ == "__main__":

    # Listen on the local machine only.
    # This setting does not expose the dashboard to the network.
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=True
    )