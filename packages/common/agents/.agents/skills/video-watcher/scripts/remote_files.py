#!/usr/bin/env python3
"""List or delete videos this skill has left on the provider.

Uploads are kept after a call so follow-up questions skip the upload; the
provider removes them itself after its retention period (about 48 hours on
Gemini). Use this to see what is still there, or to remove it sooner.

Only providers with an upload step hold files (Gemini). Uploads made by this
skill carry a display name starting with "vw-".
"""

import argparse
import json
import sys

import settings
from media import load_remote_files, save_remote_files
from providers import ProviderError, make_adapter


def fail(code: str, message: str, exit_code: int) -> None:
    print(json.dumps({"ok": False, "error": {"code": code, "message": message}}, indent=2))
    sys.exit(exit_code)


def main():
    parser = argparse.ArgumentParser(description="Manage videos uploaded to the provider")
    parser.add_argument("action", choices=("list", "delete"))
    parser.add_argument("--name", action="append", default=[], help="Remote file name to delete, e.g. files/abc123")
    parser.add_argument("--all", action="store_true", help="Delete every upload made by this skill")
    parser.add_argument("--provider")
    parser.add_argument("--base-url")
    args = parser.parse_args()

    try:
        resolved = settings.resolve(
            {"PROVIDER": args.provider, "BASE_URL": args.base_url}, require=("provider", "api_key")
        )
    except settings.ConfigError as exc:
        fail(exc.code, exc.message, 2)
    adapter = make_adapter(resolved)
    if not adapter.keeps_uploads:
        print(json.dumps({"ok": True, "files": [], "note": f"{resolved.provider} takes video inline; nothing is stored."}))
        return

    cache = load_remote_files()
    known = {entry["name"]: entry for entry in cache.values()}
    try:
        files = [f for f in adapter.list_files() if (f.get("displayName") or "").startswith("vw-")]
        if args.action == "list":
            print(json.dumps({
                "ok": True,
                "endpoint": resolved.base_url,
                "files": [{
                    "name": f.get("name"),
                    "size_bytes": int(f["sizeBytes"]) if f.get("sizeBytes") else None,
                    "created": f.get("createTime"),
                    "expires": f.get("expirationTime"),
                    "state": f.get("state"),
                    "local_video": (known.get(f.get("name")) or {}).get("video"),
                } for f in files],
            }, indent=2))
            return

        if not args.name and not args.all:
            fail("nothing_selected", "Pass --name <files/...> or --all.", 1)
        targets = [f["name"] for f in files] if args.all else args.name
        deleted = [name for name in targets if adapter.delete_remote(name)]
    except ProviderError as exc:
        fail("provider_error", exc.message, 4)

    remaining = {key: entry for key, entry in cache.items() if entry["name"] not in deleted}
    if len(remaining) != len(cache):
        save_remote_files(remaining)
    print(json.dumps({"ok": True, "deleted": deleted, "not_found": [n for n in targets if n not in deleted]}, indent=2))


if __name__ == "__main__":
    main()
