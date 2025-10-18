# streamlit_app.py
"""
Safe Streamlit SMS demo.

Modes:
- Simulation: no network calls; useful for UI/demo/testing.
- Twilio: send through Twilio REST API (legitimate provider).
  Requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER env vars.

Security measures:
- Explicit consent checkbox required before sending.
- Simple per-session rate limiting (min_delay_seconds).
- Local logging to sent.log (UTC timestamps) for auditing.

IMPORTANT: Twilio mode will only attempt to send if the environment variables
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER are present.
Do NOT use Twilio mode for unsolicited messages, spoofing, or harassment.
"""

import os
import time
import logging
from datetime import datetime, timezone

import streamlit as st

# Optional: use twilio library only if user activates Twilio mode
try:
    from twilio.rest import Client as TwilioClient
    HAS_TWILIO = True
except Exception:
    HAS_TWILIO = False

# -------- CONFIG ----------
LOG_FILE = "sent.log"
MIN_DELAY_SECONDS = 1.0  # minimum seconds between sends (simple rate limit)
# --------------------------

# Setup logging to file (appends)
logger = logging.getLogger("sms_app")
logger.setLevel(logging.INFO)
handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
handler.setFormatter(logging.Formatter("%(message)s"))
if not logger.handlers:
    logger.addHandler(handler)


def log_entry(mode: str, to_number: str, message: str, status: str, extra: str = ""):
    """Write a single-line log entry with UTC ISO timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    safe_message = message.replace("\n", " ").replace("\t", " ")
    safe_extra = extra.replace("\n", " ").replace("\t", " ")
    line = f"{now}\t{mode}\t{to_number}\t{status}\t{safe_extra}\t{safe_message}"
    logger.info(line)

# Session-state helpers for basic rate limiting & history
if "last_send_time" not in st.session_state:
    st.session_state.last_send_time = 0.0
if "history" not in st.session_state:
    st.session_state.history = []

st.set_page_config(page_title="Safe SMS Demo", page_icon="✉️")

st.title("Safe SMS Demo — Streamlit")
st.caption("This app demonstrates a safe UI for sending SMS. Use Simulation mode to test, or Twilio mode for legitimate sending.")

# Mode selector
mode = st.selectbox("Mode", ["Simulation (no network)", "Twilio (real SMS)"])

st.markdown("---")
st.subheader("Message details")
to_number = st.text_input("Recipient phone number (E.164 recommended, e.g. +14155552671)")
message = st.text_area("Message", height=120, placeholder="Type the SMS message here...")
consent = st.checkbox("I confirm I have permission to message this recipient and will not use this for spam/harassment.", value=False)

# Twilio credentials info (hidden unless Twilio mode selected)
if mode.startswith("Twilio"):
    st.info("Twilio mode requires environment variables: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER.")
    if not HAS_TWILIO:
        st.warning("Twilio library (twilio) is not installed in this environment. Install with `pip install twilio` to enable Twilio sending.")
    twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    twilio_from = os.environ.get("TWILIO_FROM_NUMBER", "")

    if not twilio_sid or not twilio_token or not twilio_from:
        st.warning("TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN or TWILIO_FROM_NUMBER not set in environment. Twilio sending will not work until set.")

send_button = st.button("Send message")


def can_send():
    now = time.time()
    elapsed = now - st.session_state.last_send_time
    if elapsed < MIN_DELAY_SECONDS:
        st.error(f"Please wait {MIN_DELAY_SECONDS - elapsed:.1f}s before sending another message (rate limit).")
        return False
    if not to_number.strip():
        st.error("Recipient number is required.")
        return False
    if not message.strip():
        st.error("Message is empty.")
        return False
    if not consent:
        st.error("You must confirm you have permission to message this recipient.")
        return False
    return True

if send_button:
    if not can_send():
        st.stop()

    st.session_state.last_send_time = time.time()
    mode_label = "simulation" if mode.startswith("Simulation") else "twilio"

    if mode_label == "simulation":
        # Simulate send: no external network call
        simulated_status = "SIMULATED_OK"
        simulated_resp = f"Simulated send to {to_number} at {datetime.now(timezone.utc).isoformat()}"
        st.success("Simulation: message queued (no network call).")
        st.info(simulated_resp)
        st.session_state.history.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "to": to_number,
            "message": message,
            "status": simulated_status,
        })
        log_entry("simulation", to_number, message, simulated_status, extra=simulated_resp)

    else:
        # Twilio mode
        if not HAS_TWILIO:
            st.error("Twilio SDK is not available. Install `twilio` and restart the app.")
            log_entry("twilio", to_number, message, "FAILED", extra="twilio sdk not installed")
            st.stop()

        twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        twilio_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        twilio_from = os.environ.get("TWILIO_FROM_NUMBER", "")

        if not (twilio_sid and twilio_token and twilio_from):
            st.error("Missing Twilio credentials in environment variables. Twilio mode requires: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER.")
            log_entry("twilio", to_number, message, "FAILED", extra="missing credentials")
            st.stop()

        # Create client and attempt send
        try:
            client = TwilioClient(twilio_sid, twilio_token)
            msg = client.messages.create(
                body=message,
                from_=twilio_from,
                to=to_number
            )
            status = getattr(msg, "status", "sent")
            sid = getattr(msg, "sid", "")
            st.success(f"Message sent: SID={sid} status={status}")
            st.write("Twilio response object summary:")
            st.json({"sid": sid, "status": status})
            st.session_state.history.append({
                "time": datetime.now(timezone.utc).isoformat(),
                "to": to_number,
                "message": message,
                "status": status,
                "sid": sid
            })
            log_entry("twilio", to_number, message, status, extra=f"sid={sid}")

        except Exception as e:
            err_msg = str(e)
            st.error(f"Failed to send via Twilio: {err_msg}")
            log_entry("twilio", to_number, message, "FAILED", extra=err_msg)

st.markdown("---")
st.subheader("Recent session sends")
if st.session_state.history:
    for i, h in enumerate(reversed(st.session_state.history[-10:]), 1):
        st.write(f"{i}. [{h['time']}] → {h['to']} — status: {h.get('status')}")
        # collapse message
        with st.expander("Show message"):
            st.write(h.get("message"))

st.markdown("---")
st.caption("Logs are appended to local file 'sent.log' (UTC timestamps). This app enforces a minimal rate limit and requires explicit consent. Do not use for unsolicited messages or spoofing.")

# -------------------
# requirements.txt
# -------------------
streamlit==1.38.0
twilio==9.8.0

# -------------------
# Procfile
# -------------------
web: streamlit run streamlit_app.py --server.port=$PORT --server.enableCORS=false

# -------------------
# Dockerfile
# -------------------
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt
EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.enableCORS=false"]
