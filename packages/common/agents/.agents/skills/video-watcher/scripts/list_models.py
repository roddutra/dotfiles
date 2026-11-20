#!/usr/bin/env python3
"""List the models the configured provider offers, for choosing VIDEO_WATCHER_MODEL.

Model names change often, so the skill never hardcodes one. Where the provider
reports input modalities (OpenRouter does), only video-capable models are
listed. Gemini's model list does not report modalities; consult its docs when
unsure whether a model accepts video.
"""

import argparse
import json
import sys

import settings
from providers import ProviderError, make_adapter


def main():
    parser = argparse.ArgumentParser(description="List models from the configured provider")
    parser.add_argument("--provider")
    parser.add_argument("--base-url")
    parser.add_argument("--filter", help="Only ids or names containing this text")
    parser.add_argument("--all", action="store_true", help="Include models not known to accept video")
    args = parser.parse_args()

    try:
        resolved = settings.resolve(
            {"PROVIDER": args.provider, "BASE_URL": args.base_url}, require=("provider", "api_key")
        )
    except settings.ConfigError as exc:
        print(json.dumps({"ok": False, "error": {"code": exc.code, "message": exc.message}}, indent=2))
        sys.exit(2)
    try:
        models = make_adapter(resolved).list_models()
    except ProviderError as exc:
        print(json.dumps({"ok": False, "error": {"code": "provider_error", "message": exc.message}}, indent=2))
        sys.exit(4)

    modalities_known = any(model["video_input"] is not None for model in models)
    if modalities_known and not args.all:
        models = [model for model in models if model["video_input"]]
    if args.filter:
        needle = args.filter.lower()
        models = [m for m in models if needle in (m["id"] or "").lower() or needle in (m["name"] or "").lower()]
    for model in models:
        model.pop("description", None)
    print(json.dumps({
        "ok": True,
        "provider": resolved.provider,
        "base_url": resolved.base_url,
        "video_input_known": modalities_known,
        "models": sorted(models, key=lambda m: m["id"] or ""),
    }, indent=2))


if __name__ == "__main__":
    main()
