from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .model import atomic_write_json, atomic_write_text, expand_path


AUTH_ROOT = "~/.local/share/nfragakis-calendar-dashboard/auth"


def google_auth(args: argparse.Namespace) -> dict[str, object]:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as error:
        raise RuntimeError("Google auth dependencies are missing; run sync/setup --direct-deps") from error
    token_path = expand_path(f"{AUTH_ROOT}/google-{args.account}.json")
    flow = InstalledAppFlow.from_client_secrets_file(
        str(expand_path(args.client_secrets)),
        ["https://www.googleapis.com/auth/calendar.readonly"],
    )
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    atomic_write_json(token_path, json.loads(credentials.to_json()))
    return {
        "type": "google",
        "account": args.account,
        "tokenFile": str(token_path),
        "selectedOnly": True,
    }


def microsoft_auth(args: argparse.Namespace) -> dict[str, object]:
    try:
        import msal
    except ImportError as error:
        raise RuntimeError("Microsoft auth dependency is missing; run sync/setup --direct-deps") from error
    cache_path = expand_path(f"{AUTH_ROOT}/microsoft-{args.account}.cache")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = msal.SerializableTokenCache()
    if cache_path.exists():
        cache.deserialize(cache_path.read_text(encoding="utf-8"))
    app = msal.PublicClientApplication(
        args.client_id,
        authority=f"https://login.microsoftonline.com/{args.tenant}",
        token_cache=cache,
    )
    result = app.acquire_token_interactive(scopes=["Calendars.Read"])
    if "access_token" not in result:
        raise RuntimeError(result.get("error_description") or "Microsoft authentication failed")
    atomic_write_text(cache_path, cache.serialize())
    return {
        "type": "microsoft",
        "account": args.account,
        "clientId": args.client_id,
        "tenant": args.tenant,
        "tokenCache": str(cache_path),
    }


def build_parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Authenticate a direct calendar provider")
    subparsers = result.add_subparsers(dest="provider", required=True)
    google = subparsers.add_parser("google")
    google.add_argument("--account", required=True)
    google.add_argument("--client-secrets", required=True)
    google.set_defaults(handler=google_auth)
    microsoft = subparsers.add_parser("microsoft")
    microsoft.add_argument("--account", required=True)
    microsoft.add_argument("--client-id", required=True)
    microsoft.add_argument("--tenant", default="organizations")
    microsoft.set_defaults(handler=microsoft_auth)
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    provider = args.handler(args)
    print("Add this object to the providers array in ~/.config/omarchy/calendar-dashboard.json:")
    print(json.dumps(provider, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
