#!/usr/bin/env python3
"""Print today's Breeze login URL (API key read from .env and URL-encoded).
Open it, log in, and copy the `apisession` value from the address bar into BREEZE_SESSION in .env."""
from ic.breeze_client import login_url

if __name__ == "__main__":
    print(login_url())
