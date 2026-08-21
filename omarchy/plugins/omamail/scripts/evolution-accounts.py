#!/usr/bin/python3

"""List the Google addresses Evolution Data Server can broker a token for.

One JSON line on stdout: {"accounts":["you@gmail.com", ...]}. Only addresses
are printed — never a token, never a refresh token. The setup page uses this to
offer the accounts Evolution already holds a grant for, so a mailbox EDS knows
about needs no OAuth client of its own.

An address appears here when a source is enabled and its authentication method
is Google. That is the same test evolution-token.py applies, so anything listed
is something the broker will answer for.
"""

import json
import sys

import gi

gi.require_version("EDataServer", "1.2")
from gi.repository import EDataServer  # noqa: E402


def main():
    try:
        registry = EDataServer.SourceRegistry.new_sync(None)
    except Exception as error:
        # No registry is the ordinary state on a desktop without Evolution
        # installed, not a failure worth a non-zero exit: the caller's next
        # move is the same either way, and an error code would make the setup
        # page report a broken system rather than an absent one.
        print(json.dumps({"accounts": [], "error": str(error)}, separators=(",", ":")))
        return 0

    seen = []
    for source in registry.list_sources(None):
        if not source.get_enabled():
            continue
        if not source.has_extension(EDataServer.SOURCE_EXTENSION_AUTHENTICATION):
            continue
        auth = source.get_extension(EDataServer.SOURCE_EXTENSION_AUTHENTICATION)
        if (auth.get_method() or "").strip().lower() != "google":
            continue
        user = (auth.get_user() or "").strip().lower()
        # A Google collection is several sources sharing one address — the
        # collection, its mail account, its transport, its identity. The setup
        # page offers mailboxes, not sources, so they collapse to one entry.
        if "@" not in user or user in seen:
            continue
        seen.append(user)

    print(json.dumps({"accounts": seen}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
