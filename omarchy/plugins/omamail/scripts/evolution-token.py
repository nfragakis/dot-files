#!/usr/bin/python3

"""Obtain a live Google access token from Evolution Data Server.

The token is written only to stdout, where Quickshell reads it through a pipe.
Evolution owns the refresh token and refreshes it through its verified Google
OAuth client; Omamail never reads or stores that refresh token.
"""

import json
import sys

import gi

gi.require_version("EDataServer", "1.2")
from gi.repository import EDataServer  # noqa: E402


def fail(message, exit_code=1):
    print(message, file=sys.stderr)
    raise SystemExit(exit_code)


def main():
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        fail("usage: evolution-token.py account@example.com", 2)

    account = sys.argv[1].strip().lower()
    try:
        registry = EDataServer.SourceRegistry.new_sync(None)
        candidates = []
        for source in registry.list_sources(None):
            if not source.get_enabled():
                continue
            if not source.has_extension(EDataServer.SOURCE_EXTENSION_AUTHENTICATION):
                continue
            auth = source.get_extension(EDataServer.SOURCE_EXTENSION_AUTHENTICATION)
            if (auth.get_method() or "").strip().lower() != "google":
                continue
            if (auth.get_user() or "").strip().lower() != account:
                continue
            candidates.append(source)

        if not candidates:
            fail("No Evolution Google account matches " + account, 3)

        candidates.sort(
            key=lambda source: 0
            if source.has_extension(EDataServer.SOURCE_EXTENSION_MAIL_ACCOUNT)
            else 1
        )
        success, access_token, expires_in = candidates[0].get_oauth2_access_token_sync(None)
    except Exception as error:
        fail("Evolution could not provide a Google session: " + str(error), 4)

    if not success or not access_token:
        fail("Evolution returned no Google access token", 4)

    print(
        json.dumps(
            {
                "accessToken": access_token,
                "expiresIn": max(60, int(expires_in or 3600)),
                "scope": "https://mail.google.com/",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
