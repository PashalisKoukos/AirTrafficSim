# AirTrafficSim (ATSP)

A multi-component air traffic control simulation written in Python. Simulated aircraft broadcast their positions over UDP, a central server validates and stores those updates, detects loss of separation between aircraft, and issues avoidance commands. A web dashboard provides a live view of the airspace. All control and telemetry messages are authenticated with HMAC-SHA-256.

This project is intended for educational and demonstration purposes.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Dashboard](#dashboard)
- [Network Protocol](#network-protocol)
- [Security Model](#security-model)
- [Database Schema](#database-schema)
- [Simulation Details](#simulation-details)
- [Testing](#testing)
- [Limitations](#limitations)

## Features

- Simulation of five aircraft moving in a 100 x 100 unit airspace, updating once per second
- UDP telemetry between the aircraft simulator and the server
- HMAC-SHA-256 authentication on every position update and every heading command
- Server-side validation of message type, identifiers, numeric ranges, and sequence numbers
- Rejection of stale, duplicate, and malformed packets
- Conflict detection based on pairwise Euclidean distance
- Automatic, rate-limited avoidance commands sent back to the aircraft involved
- Persistent storage of aircraft state and warning history in SQLite
- Real-time web dashboard with an airspace map, flight table, statistics, and warning history

## Architecture

The system consists of three cooperating components, all started from a single entry point (`main.py`), each in its own thread.

```
                      UDP :5000 (signed POSITION)
  +------------------+ ---------------------------> +------------------+
  |  Aircraft        |                              |  UDP Server      |
  |  Simulation      | <--------------------------- |  (server.py)     |
  |  (aircraft.py)   |   UDP :5002 (signed HEADING) |                  |
  +------------------+                              +--------+---------+
                                                             |
                                                             | read / write
                                                             v
                                                    +------------------+
                                                    |  SQLite          |
                                                    |  airtraffic.db   |
                                                    +--------+---------+
                                                             ^
                                                             | read-only
                                                    +--------+---------+
                                                    |  Flask Dashboard |
                                                    |  (app.py) :5001  |
                                                    +------------------+
```

1. **Aircraft simulation** reads the initial state of each aircraft from the database, moves them each second, and sends signed position messages to the server. It also listens for signed heading commands and applies them.
2. **UDP server** verifies each incoming message, validates its content, updates the database, checks distances between all aircraft pairs, records warnings, and sends signed avoidance commands.
3. **Web dashboard** reads the database and exposes a JSON API consumed by a single-page front end.

## Project Structure

```
.
├── main.py          # Entry point: starts server, simulation, and dashboard
├── aircraft.py      # Aircraft movement simulation and command handling
├── server.py        # UDP server, validation, conflict detection, avoidance
├── app.py           # Flask dashboard and JSON API (HTML/CSS/JS embedded)
├── dataBase.py      # SQLite schema and data access functions
├── security.py      # HMAC-SHA-256 signing and verification
├── test_udp.py      # Manual test script that sends a single UDP packet
├── airtraffic.db    # SQLite database (created automatically if missing)
└── .env             # Secret key (not committed to version control)
```

## Requirements

- Python 3.8 or newer
- Third-party packages:
  - `flask`
  - `python-dotenv`

All other modules (`socket`, `sqlite3`, `hmac`, `hashlib`, `json`, `threading`, and so on) are part of the Python standard library.

## Installation

```bash
# Clone the repository
git clone https://github.com/PashalisKoukos/AirTrafficSim.git
cd AirTrafficSim

# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows

# Install dependencies
pip install flask python-dotenv
```

## Configuration

The HMAC secret key is read from the environment variable `ATSP_HMAC_KEY`. Create a `.env` file in the project root:

```env
ATSP_HMAC_KEY=replace-this-with-a-long-random-secret
```

Generate a strong key with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

The application raises an error at startup if the key is missing. Add `.env` and `airtraffic.db` to your `.gitignore`:

```gitignore
.env
airtraffic.db
__pycache__/
venv/
```

### Runtime parameters

| Parameter | Location | Default | Description |
|---|---|---|---|
| `HOST` | `server.py`, `aircraft.py` | `127.0.0.1` | Interface used for UDP communication |
| `PORT` | `server.py`, `aircraft.py` | `5000` | UDP port for position updates |
| `COMMAND_PORT` | `server.py`, `aircraft.py` | `5002` | UDP port for heading commands |
| `MIN_DISTANCE` | `server.py`, `app.py` | `10.0` | Minimum safe separation in model units |
| `AVOIDANCE_COOLDOWN` | `server.py` | `3.0` s | Minimum time between avoidance commands for the same pair |
| `MIN_COORDINATE` / `MAX_COORDINATE` | `aircraft.py` | `0.0` / `100.0` | Airspace boundaries |
| Dashboard port | `main.py`, `app.py` | `5001` | HTTP port of the web dashboard |
| `REFRESH_INTERVAL` | `app.py` | `2000` ms | Dashboard refresh period |

`MIN_DISTANCE` is defined in both `server.py` and `app.py` and the two values must be kept identical.

## Usage

Run all components together from the project directory:

```bash
python main.py
```

This starts, in order:

1. the UDP server on `127.0.0.1:5000`,
2. the aircraft simulation (command listener on `127.0.0.1:5002`),
3. the web dashboard on `http://127.0.0.1:5001`.

Press `Ctrl+C` in the terminal to stop the system.

The database path is relative (`airtraffic.db`), so start the application from the project directory.

### Running components individually

Each module can also be run on its own, in separate terminals. Start the server first:

```bash
python server.py     # UDP server
python aircraft.py   # Aircraft simulation
python app.py        # Dashboard (Flask debug mode)
```

### Resetting the simulation

Aircraft positions are persisted by the server, so a restarted simulation resumes from the last stored positions. To restore the original positions and headings:

```bash
python -c "from dataBase import reset_aircraft_positions; reset_aircraft_positions()"
```

## Dashboard

Open `http://127.0.0.1:5001` in a browser. The dashboard refreshes every two seconds and shows:

- **Statistics:** total aircraft, aircraft in normal state, aircraft in danger, and active conflicts
- **Airspace map:** a canvas rendering of each aircraft, its heading, and a warning highlight for aircraft below the separation limit
- **Flight status table:** manufacturer, origin, destination, position, speed, heading, and status
- **Warning history:** the 20 most recent warnings recorded by the server
- **Connection indicator:** reflects whether the API is reachable

### HTTP API

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Dashboard page |
| `/api/state` | GET | Current aircraft, active conflicts, recent warnings, and the distance limit as JSON |

Example response shape:

```json
{
  "aircraft": [
    {
      "aircraft_id": "AC001",
      "name": "Aegean-01",
      "x": 10.0,
      "y": 20.0,
      "speed": 2.0,
      "heading": 90.0,
      "origin": "ATH",
      "destination": "SKG",
      "manufacturer": "Airbus"
    }
  ],
  "conflicts": [
    { "aircraft_id_1": "AC001", "aircraft_id_2": "AC002", "distance": 7.5 }
  ],
  "warnings": [
    {
      "warning_id": 1,
      "aircraft_id_1": "AC001",
      "aircraft_id_2": "AC002",
      "distance": 7.5,
      "timestamp": "2026-01-01 12:00:00"
    }
  ],
  "min_distance": 10.0
}
```

Active conflicts are computed from the current positions in the database. The warning history is a log of past events and is not used to decide whether a conflict is currently active.

## Network Protocol

All messages are JSON objects carried in single UDP datagrams (maximum 4096 bytes read per packet). Every message includes an `hmac` field.

### Position update (aircraft to server, port 5000)

```json
{
  "type": "POSITION",
  "aircraft_id": "AC001",
  "seq": 42,
  "x": 55.2,
  "y": 20.0,
  "speed": 2.0,
  "heading": 90.0,
  "hmac": "<hex digest>"
}
```

### Heading command (server to aircraft, port 5002)

```json
{
  "type": "HEADING",
  "aircraft_id": "AC001",
  "heading": 212.5,
  "hmac": "<hex digest>"
}
```

### Server-side validation

A position update is accepted only if all of the following hold:

- the JSON payload is an object with a valid HMAC,
- `type` is `POSITION`,
- `aircraft_id` is a known aircraft (`AC001` to `AC005`),
- `seq` is a positive integer greater than the last accepted value for that aircraft,
- `x`, `y`, `speed`, and `heading` are finite numbers (booleans are rejected),
- `x` and `y` lie within 0 to 100, `speed` is not negative, and `heading` is within 0 to 360.

Rejected packets are logged to the console and otherwise ignored.

### Conflict handling

After each accepted update the server computes the Euclidean distance between every pair of aircraft. When a pair is closer than `MIN_DISTANCE`, the server:

1. prints a warning,
2. stores a record in the `warnings` table,
3. sends each aircraft a signed `HEADING` command pointing directly away from the other aircraft (or a 90 degree turn if both share the same position), no more than once per `AVOIDANCE_COOLDOWN` seconds for that pair.

Headings follow the convention: 0 degrees is +y, 90 degrees is +x, 180 degrees is -y, 270 degrees is -x.

## Security Model

- **Authentication and integrity.** The signature is an HMAC-SHA-256 over a canonical JSON encoding of the message (sorted keys, compact separators, `hmac` field excluded). Messages that are unsigned, altered, or signed with a different key are rejected on both sides.
- **Constant-time comparison.** Signatures are compared with `hmac.compare_digest`.
- **Replay protection on telemetry.** The server tracks the last accepted `seq` per aircraft and rejects stale or duplicate packets.
- **Secret management.** The key is loaded from the environment (`.env`) and never stored in source code.
- **Input validation.** Both the server and the aircraft validate message structure and value ranges before acting on them.
- **Safe rendering.** The dashboard inserts database values using `textContent` rather than HTML.
- **Network exposure.** All sockets and the web server bind to `127.0.0.1` only.

## Database Schema

The SQLite database `airtraffic.db` is created automatically on first run.

**`aircraft`**

| Column | Type | Notes |
|---|---|---|
| `aircraft_id` | TEXT | Primary key |
| `name` | TEXT | Callsign |
| `x`, `y` | REAL | Current position |
| `speed` | REAL | Units per update |
| `heading` | REAL | Degrees |
| `origin`, `destination` | TEXT | Airport codes |
| `manufacturer` | TEXT | Aircraft manufacturer |

**`warnings`**

| Column | Type | Notes |
|---|---|---|
| `warning_id` | INTEGER | Primary key, autoincrement |
| `aircraft_id_1`, `aircraft_id_2` | TEXT | Aircraft involved |
| `distance` | REAL | Distance at detection |
| `timestamp` | DATETIME | Local system time |

### Initial fleet

| ID | Name | Start (x, y) | Speed | Heading | Route | Manufacturer |
|---|---|---|---|---|---|---|
| AC001 | Aegean-01 | (10, 20) | 2.0 | 90 | ATH - SKG | Airbus |
| AC002 | Aegean-02 | (80, 20) | 2.0 | 270 | SKG - ATH | Airbus |
| AC003 | Sky-03 | (20, 80) | 1.5 | 180 | HER - ATH | Boeing |
| AC004 | Sky-04 | (70, 70) | 1.8 | 225 | RHO - ATH | Boeing |
| AC005 | Sky-05 | (50, 10) | 1.2 | 0 | ATH - JTR | Embraer |

## Simulation Details

- Each aircraft advances once per second: `x += speed * sin(heading)`, `y += speed * cos(heading)`.
- When an aircraft would leave the 0 to 100 area, its heading is mirrored on the relevant axis so that it bounces back into the airspace.
- Every aircraft keeps its own incrementing sequence number.
- Heading commands are verified (HMAC, type, numeric range) before being applied.

## Testing

`test_udp.py` is a manual helper that sends a single `POSITION` packet for `AC001` at the exact coordinates of `AC002`, using the current values from the database. The script does not sign the message, so the server rejects it with an HMAC failure. This makes it a quick check that authentication is enforced. To simulate a valid close-approach event, add an `hmac` field computed with `create_hmac` from `security.py` before sending.

To run it, start the server first, then:

```bash
python test_udp.py
```

## Limitations

- HMAC provides authentication and integrity, not confidentiality. Messages are sent in plaintext.
- Heading commands carry no sequence number or timestamp, so a captured command could be replayed within the same key lifetime.
- A single shared secret is used by all participants; there is no per-aircraft key or key rotation.
- UDP offers no delivery or ordering guarantees; lost packets are simply skipped.
- The server runs distance checks on every accepted update and opens a new database connection per query, which is simple but not optimized for scale.
- Conflict avoidance is a simple geometric heuristic and does not guarantee resolution.
- The dashboard is served by the Flask development server and is intended for local use only.
- The model uses abstract units and does not represent real-world distances, altitudes, or aircraft performance.
