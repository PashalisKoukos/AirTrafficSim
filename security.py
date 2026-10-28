# ---------------------------------------------------------
# security.py
# Message authentication for the ATSP system using HMAC-SHA-256.
#
# The secret key is stored in a .env file (environment variable
# ATSP_HMAC_KEY) and is never hard-coded in the source code.
# ---------------------------------------------------------

import hashlib
import hmac
import json
import os

from dotenv import load_dotenv


# Load the variables defined in the .env file into the environment.
load_dotenv()

# Read the secret key from the environment.
secret_key = os.getenv("ATSP_HMAC_KEY")

# Fail early with a clear message if the key is missing.
if not secret_key:
    raise RuntimeError(
        "ATSP_HMAC_KEY was not found. "
        "Make sure a .env file exists and contains the secret key."
    )

# The HMAC function requires the key as bytes, not text.
HMAC_SECRET_KEY = secret_key.encode("utf-8")


def create_hmac(message):
    """
    Create an HMAC-SHA-256 signature for a message.

    The message must be a Python dict. The signature is computed
    over a canonical JSON encoding of the data, so the receiver can
    detect whether the message was modified in transit.
    """

    # Serialize the dict to JSON with sorted keys and compact
    # separators. This guarantees that both sides produce
    # identical bytes for identical messages.
    message_json = json.dumps(
        message,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False
    )

    # Convert the JSON text to bytes for hashing.
    message_bytes = message_json.encode("utf-8")

    # Compute the signature using HMAC with SHA-256.
    signature = hmac.new(
        HMAC_SECRET_KEY,
        message_bytes,
        hashlib.sha256
    ).hexdigest()

    # Return the signature as a hexadecimal string.
    return signature


def verify_hmac(message, received_signature):
    """
    Check whether a received signature matches the given message.

    Returns:
        True  -> the signature is valid
        False -> the signature is wrong, or the message cannot
                 be serialized for signing
    """

    # The received signature must be a string.
    if not isinstance(received_signature, str):
        return False

    try:
        # Recompute the signature we expect for this message.
        expected_signature = create_hmac(message)

        # Compare in constant time to avoid timing attacks.
        return hmac.compare_digest(
            expected_signature,
            received_signature
        )

    except (TypeError, ValueError):
        # If the message cannot be serialized to JSON correctly
        # (for example it contains NaN), treat it as invalid.
        return False