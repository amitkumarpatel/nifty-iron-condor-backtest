"""Breeze login helpers. Credentials come from .env (loaded by ic.config)."""
import getpass
import os
import urllib.parse

from ic import config  # noqa: F401  (importing loads .env)


def _get(name, prompt, secret=True):
    v = os.environ.get(name, "").strip()
    if v:
        return v
    return getpass.getpass(prompt) if secret else input(prompt).strip()


def login_url() -> str:
    key = _get("BREEZE_API_KEY", "API key: ")
    return "https://api.icicidirect.com/apiuser/login?api_key=" + urllib.parse.quote_plus(key)


def connect():
    """Return a logged-in BreezeConnect client."""
    from breeze_connect import BreezeConnect
    key = _get("BREEZE_API_KEY", "API key: ")
    secret = _get("BREEZE_API_SECRET", "API secret: ")
    session = _get("BREEZE_SESSION", "Today's API_Session token: ", secret=False)
    b = BreezeConnect(api_key=key)
    try:
        b.generate_session(api_secret=secret, session_token=session)
    except Exception as e:
        raise SystemExit(
            f"Breeze login failed: {e}\n"
            "The session token changes every day. Run `python login_url.py`, log in, copy the "
            "apisession value from the address bar into BREEZE_SESSION in .env, and try again.")
    return b
