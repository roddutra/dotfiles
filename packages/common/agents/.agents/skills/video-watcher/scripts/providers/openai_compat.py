"""OpenAI-compatible adapter: chat completions with a `video_url` content part.

Covers OpenRouter and any endpoint that accepts the same request. These APIs
have no upload step, so the whole file travels inline as a base64 data URL.
That makes file size the binding limit, and time windows need a file that was
trimmed locally first (prepare.py).

This path was written from the OpenRouter docs (November 2026) and has not
been exercised against a live endpoint.
"""

import base64
import json

from http_util import ApiError, request_json
from providers import PreflightError, ProviderError

DEFAULT_MAX_INLINE_MB = 50

MIME_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/mov",
    ".webm": "video/webm",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
}


class OpenAICompatAdapter:
    name = "openai_compat"
    keeps_uploads = False

    def __init__(self, resolved):
        self.base_url = resolved.base_url
        self.api_key = resolved.api_key
        self.model = resolved.model

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def list_models(self) -> list[dict]:
        try:
            data, _ = request_json("GET", f"{self.base_url}/models", self._headers())
        except ApiError as exc:
            raise ProviderError(exc.message, exc.status) from None
        models = []
        for model in data.get("data", []):
            modalities = (model.get("architecture") or {}).get("input_modalities")
            models.append({
                "id": model.get("id"),
                "name": model.get("name"),
                "input_token_limit": model.get("context_length"),
                "output_token_limit": (model.get("top_provider") or {}).get("max_completion_tokens"),
                "video_input": ("video" in modalities) if isinstance(modalities, list) else None,
                "description": None,
            })
        return models

    def model_limits(self) -> dict | None:
        try:
            models = self.list_models()
        except ProviderError:
            return None
        for model in models:
            if model["id"] == self.model:
                return {"input_tokens": model["input_token_limit"], "output_tokens": model["output_token_limit"]}
        return None

    def mime_type(self, video) -> str | None:
        return MIME_TYPES.get(video.path.suffix.lower())

    def check_transport(self, video, options) -> None:
        if self.mime_type(video) is None:
            raise PreflightError(
                "unsupported_container",
                f"{video.path.suffix or 'This file type'} is not accepted here ({', '.join(sorted(MIME_TYPES))}).",
                ["Run prepare.py to transcode it to mp4."],
            )
        limit_mb = options.get("max_inline_mb") or DEFAULT_MAX_INLINE_MB
        if video.size > limit_mb * 1024 ** 2:
            raise PreflightError(
                "file_too_large",
                f"The video is {video.size / 1024 ** 2:.0f} MB. This provider takes video inline as base64, "
                f"and the limit set here is {limit_mb} MB.",
                ["Run prepare.py to shrink or trim it.",
                 "Raise the limit with --max-inline-mb if the endpoint accepts larger requests.",
                 "Use the gemini provider, which uploads files up to 2 GB."],
            )
        if options.get("start") is not None or options.get("end") is not None:
            raise PreflightError(
                "window_unsupported",
                "This provider cannot select a time window from an inline video.",
                ["Run prepare.py with --start/--end and send the trimmed file."],
            )

    def ensure_video(self, video, options, log) -> dict:
        return {
            "path": str(video.path),
            "mime_type": self.mime_type(video),
            "duration_seconds": video.duration,
            "name": None,
            "expires": None,
            "reused": False,
        }

    def estimate_video_tokens(self, seconds: float, options) -> int | None:
        return None

    def delete_remote(self, name: str) -> bool:
        return False

    def run(self, handle: dict, request_spec: dict, log) -> dict:
        notes = []
        for option in ("fps", "resolution"):
            if request_spec.get(option):
                notes.append(f"--{option} is not supported by this provider and was ignored.")
        with open(handle["path"], "rb") as source:
            encoded = base64.b64encode(source.read()).decode("ascii")
        texts = request_spec["texts"]
        content = [{"type": "text", "text": text} for text in texts[:-1]]
        content.append({"type": "video_url", "video_url": {"url": f"data:{handle['mime_type']};base64,{encoded}"}})
        content.append({"type": "text", "text": texts[-1]})
        payload = {"model": self.model, "messages": [{"role": "user", "content": content}]}
        if request_spec.get("max_output_tokens"):
            payload["max_tokens"] = request_spec["max_output_tokens"]
        body = json.dumps(payload).encode()
        del encoded, content, payload
        log(f"Sending {len(body) / 1024 ** 2:.0f} MB inline to {self.base_url}")
        try:
            data, _ = request_json(
                "POST", f"{self.base_url}/chat/completions", self._headers(), body,
                timeout=request_spec.get("timeout", 1800), retries=0,
            )
        except ApiError as exc:
            raise ProviderError(exc.message, exc.status) from None
        if isinstance(data.get("error"), dict):
            raise ProviderError(data["error"].get("message") or json.dumps(data["error"])[:500])
        choice = (data.get("choices") or [{}])[0]
        message = (choice.get("message") or {}).get("content")
        if isinstance(message, list):
            message = "".join(part.get("text", "") for part in message if isinstance(part, dict))
        if not message:
            raise ProviderError(f"The model returned no text (finish reason: {choice.get('finish_reason')!r}).")
        if choice.get("finish_reason") == "length":
            notes.append("The answer was cut off by the output token limit.")
        usage = data.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        return {
            "text": message,
            "status": choice.get("finish_reason"),
            "notes": notes,
            "usage": {
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "thought_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "video_tokens": details.get("video_tokens"),
                "audio_tokens": details.get("audio_tokens"),
                "cost": usage.get("cost"),
            },
        }
