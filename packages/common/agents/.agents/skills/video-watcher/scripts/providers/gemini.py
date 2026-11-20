"""Gemini adapter: Files API upload plus the Interactions API.

The video is uploaded once (resumable, in chunks, never held in memory whole)
and referenced by URI, so time windows, frame rate and resolution are applied
by the API with no local transcode. Uploads expire on Google's side after
about 48 hours.

Wire details were checked against the Gemini API docs in November 2026. The
numbers below are that documentation's; they feed estimates and limits only,
so a stale value produces a wrong estimate, never a wrong answer.
"""

import json
import time
from urllib.parse import quote

from http_util import ApiError, request, request_json
from providers import PreflightError, ProviderError

API_REVISION = "2026-05-20"

# Files API: per-file maximum.
FILE_LIMIT_BYTES = 2 * 1024 ** 3

# Token accounting for current Gemini models: frames are sampled at 1 fps by
# default, low and medium resolution cost the same per frame, audio is
# charged per second.
DEFAULT_FPS = 1.0
TOKENS_PER_FRAME = {"low": 70, "medium": 70, "high": 280}
AUDIO_TOKENS_PER_SECOND = 25

UPLOAD_CHUNK_BYTES = 32 * 1024 ** 2
DEFAULT_GRANULARITY = 8 * 1024 ** 2

MIME_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/mov",
    ".webm": "video/webm",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpg",
    ".avi": "video/avi",
    ".flv": "video/x-flv",
    ".wmv": "video/wmv",
    ".3gp": "video/3gpp",
}

TERMINAL_STATUSES = ("completed", "failed", "cancelled", "incomplete")


def _seconds(value) -> float | None:
    """Parse a duration such as "5400s" or "12.5s"."""
    if value is None:
        return None
    try:
        return float(str(value).rstrip("s"))
    except ValueError:
        return None


class GeminiAdapter:
    name = "gemini"
    keeps_uploads = True

    def __init__(self, resolved):
        self.base_url = resolved.base_url
        self.api_key = resolved.api_key
        self.model = (resolved.model or "").removeprefix("models/")

    def _headers(self, extra: dict | None = None) -> dict:
        return {"x-goog-api-key": self.api_key, **(extra or {})}

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _get_pages(self, path: str, field: str) -> list[dict]:
        """Collect every page of a list endpoint."""
        items, token = [], None
        while True:
            url = self._url(path)
            if token:
                url += f"&pageToken={quote(token)}"
            try:
                page, _ = request_json("GET", url, self._headers())
            except ApiError as exc:
                raise ProviderError(exc.message, exc.status) from None
            items.extend(page.get(field, []))
            token = page.get("nextPageToken")
            if not token:
                return items

    # Models

    def list_models(self) -> list[dict]:
        return [{
            "id": model.get("name", "").removeprefix("models/"),
            "name": model.get("displayName"),
            "input_token_limit": model.get("inputTokenLimit"),
            "output_token_limit": model.get("outputTokenLimit"),
            # The Gemini model list does not say which models accept video.
            "video_input": None,
            "description": model.get("description"),
        } for model in self._get_pages("/v1beta/models?pageSize=1000", "models")]

    def model_limits(self) -> dict | None:
        try:
            model, _ = request_json("GET", self._url(f"/v1beta/models/{quote(self.model)}"), self._headers())
        except ApiError as exc:
            if exc.status == 404:
                raise ProviderError(f"Model {self.model!r} was not found at {self.base_url}.", exc.status) from None
            raise ProviderError(exc.message, exc.status) from None
        return {"input_tokens": model.get("inputTokenLimit"), "output_tokens": model.get("outputTokenLimit")}

    # Transport

    def mime_type(self, video) -> str | None:
        return MIME_TYPES.get(video.path.suffix.lower())

    def check_transport(self, video, options) -> None:
        if self.mime_type(video) is None:
            raise PreflightError(
                "unsupported_container",
                f"{video.path.suffix or 'This file type'} is not a container Gemini accepts "
                f"({', '.join(sorted(MIME_TYPES))}).",
                ["Run prepare.py to transcode it to mp4."],
            )
        if video.size > FILE_LIMIT_BYTES:
            raise PreflightError(
                "file_too_large",
                f"The video is {video.size / 1024 ** 3:.2f} GB; Gemini's Files API accepts up to "
                f"{FILE_LIMIT_BYTES / 1024 ** 3:.0f} GB per file.",
                ["Run prepare.py to shrink it (keeps resolution, lowers frame rate and bitrate).",
                 "Run prepare.py with --start/--end to send only part of it."],
            )

    def get_file(self, name: str) -> dict | None:
        """File metadata, or None when it is gone or not ours."""
        try:
            data, _ = request_json("GET", self._url(f"/v1beta/{name}"), self._headers())
        except ApiError as exc:
            if exc.status in (400, 403, 404):
                return None
            raise ProviderError(exc.message, exc.status) from None
        return data

    def list_files(self) -> list[dict]:
        return self._get_pages("/v1beta/files?pageSize=100", "files")

    def delete_remote(self, name: str) -> bool:
        try:
            request_json("DELETE", self._url(f"/v1beta/{name}"), self._headers())
        except ApiError as exc:
            if exc.status in (403, 404):
                return False
            raise ProviderError(exc.message, exc.status) from None
        return True

    def _upload(self, video, mime: str, display_name: str, log) -> dict:
        try:
            _, headers = request_json(
                "POST",
                self._url("/upload/v1beta/files"),
                self._headers({
                    "X-Goog-Upload-Protocol": "resumable",
                    "X-Goog-Upload-Command": "start",
                    "X-Goog-Upload-Header-Content-Length": str(video.size),
                    "X-Goog-Upload-Header-Content-Type": mime,
                }),
                {"file": {"display_name": display_name}},
            )
        except ApiError as exc:
            raise ProviderError(f"Could not start the upload: {exc.message}", exc.status) from None
        upload_url = headers.get("x-goog-upload-url")
        if not upload_url:
            raise ProviderError("The upload start response carried no upload URL.")
        granularity = int(headers.get("x-goog-upload-chunk-granularity") or DEFAULT_GRANULARITY)
        chunk_size = max(granularity, UPLOAD_CHUNK_BYTES // granularity * granularity)

        offset, failures, last_logged = 0, 0, -1
        with video.path.open("rb") as handle:
            while True:
                handle.seek(offset)
                chunk = handle.read(chunk_size)
                final = offset + len(chunk) >= video.size
                try:
                    _, _, raw = request(
                        "POST",
                        upload_url,
                        self._headers({
                            "Content-Length": str(len(chunk)),
                            "X-Goog-Upload-Offset": str(offset),
                            "X-Goog-Upload-Command": "upload, finalize" if final else "upload",
                        }),
                        chunk,
                        timeout=600,
                        retries=0,
                    )
                except ApiError as exc:
                    failures += 1
                    if failures > 5 or (exc.status is not None and exc.status < 500 and exc.status != 429):
                        raise ProviderError(f"Upload failed at byte {offset}: {exc.message}", exc.status) from None
                    time.sleep(min(2 ** failures, 30))
                    status, received = self._upload_progress(upload_url)
                    if status == "final":
                        return self._find_uploaded(display_name)
                    if received is not None:
                        offset = received
                    continue
                failures = 0
                offset += len(chunk)
                percent = int(offset * 100 / video.size)
                if percent // 10 != last_logged:
                    last_logged = percent // 10
                    log(f"Uploaded {percent}% ({offset / 1024 ** 2:.0f} MB)")
                if final:
                    try:
                        return json.loads(raw)["file"]
                    except (ValueError, KeyError):
                        return self._find_uploaded(display_name)

    def _upload_progress(self, upload_url: str):
        """Ask the server how much of an interrupted upload it has."""
        try:
            _, headers, _ = request(
                "POST", upload_url, self._headers({"X-Goog-Upload-Command": "query"}), b"", timeout=60, retries=2
            )
        except ApiError:
            return None, None
        received = headers.get("x-goog-upload-size-received")
        return headers.get("x-goog-upload-status"), int(received) if received and received.isdigit() else None

    def _find_uploaded(self, display_name: str) -> dict:
        matches = [f for f in self.list_files() if f.get("displayName") == display_name]
        if not matches:
            raise ProviderError("The upload finished but the file could not be found afterwards.")
        return max(matches, key=lambda f: f.get("createTime", ""))

    def _wait_active(self, name: str, timeout: float, log) -> dict:
        deadline = time.monotonic() + timeout
        announced = False
        while True:
            data = self.get_file(name)
            if data is None:
                raise ProviderError(f"Uploaded file {name} disappeared while processing.")
            state = data.get("state")
            if state == "ACTIVE":
                return data
            if state == "FAILED":
                detail = (data.get("error") or {}).get("message", "no reason given")
                raise ProviderError(f"Gemini could not process the video: {detail}")
            if time.monotonic() > deadline:
                raise ProviderError(f"The video was still processing after {timeout:.0f} seconds ({name}).")
            if not announced:
                log("Waiting for Gemini to process the upload")
                announced = True
            time.sleep(5)

    def _handle(self, data: dict, reused: bool) -> dict:
        metadata = data.get("videoMetadata") or (data.get("metadata") or {}).get("videoMetadata") or {}
        return {
            "name": data.get("name"),
            "uri": data.get("uri"),
            "mime_type": data.get("mimeType"),
            "expires": data.get("expirationTime"),
            "duration_seconds": _seconds(metadata.get("videoDuration")),
            "reused": reused,
        }

    def ensure_video(self, video, options, log) -> dict:
        """Reuse a live upload of the same bytes, or upload the file."""
        cached = options.get("cached_remote")
        if cached:
            data = self.get_file(cached["name"])
            if data is not None and data.get("state") == "ACTIVE":
                log(f"Reusing the earlier upload ({cached['name']})")
                return self._handle(data, reused=True)
        mime = self.mime_type(video)
        log(f"Uploading {video.size / 1024 ** 2:.0f} MB to {self.base_url}")
        data = self._upload(video, mime, f"vw-{video.sha256[:16]}", log)
        if data.get("state") != "ACTIVE":
            data = self._wait_active(data["name"], options.get("processing_timeout", 900), log)
        return self._handle(data, reused=False)

    # Model call

    def estimate_video_tokens(self, seconds: float, options) -> int | None:
        fps = options.get("fps") or DEFAULT_FPS
        per_frame = TOKENS_PER_FRAME.get(options.get("resolution") or "medium", 70)
        return int(seconds * (fps * per_frame + AUDIO_TOKENS_PER_SECOND))

    def _payload(self, handle: dict, request_spec: dict) -> dict:
        video_part = {"type": "video", "uri": handle["uri"], "mime_type": handle["mime_type"]}
        processing = {}
        if request_spec.get("start") is not None:
            processing["start_offset"] = f"{request_spec['start']:g}s"
        if request_spec.get("end") is not None:
            processing["end_offset"] = f"{request_spec['end']:g}s"
        if request_spec.get("fps"):
            processing["fps"] = request_spec["fps"]
        if processing:
            video_part["processing"] = {"type": "static", **processing}
        if request_spec.get("resolution"):
            video_part["resolution"] = request_spec["resolution"]
        payload = {
            "model": self.model,
            "input": [video_part] + [{"type": "text", "text": text} for text in request_spec["texts"]],
        }
        if request_spec.get("max_output_tokens"):
            payload["generation_config"] = {"max_output_tokens": request_spec["max_output_tokens"]}
        return payload

    def run(self, handle: dict, request_spec: dict, log) -> dict:
        """Run in the background and poll, so a slow answer survives a dropped connection.

        Background runs are stored by the API, so the interaction is deleted
        once its answer has been read.
        """
        payload = self._payload(handle, request_spec)
        headers = self._headers({"Api-Revision": API_REVISION})
        timeout = request_spec.get("timeout", 1800)
        notes = []
        try:
            interaction, _ = request_json(
                "POST", self._url("/v1beta/interactions"), headers, {**payload, "background": True}, retries=1
            )
        except ApiError as exc:
            if exc.status == 400 and "background" in exc.message.lower():
                notes.append("This model does not run in the background; the request was sent as one blocking call.")
                return self._run_blocking(payload, headers, timeout, notes)
            raise ProviderError(exc.message, exc.status) from None

        interaction_id = interaction.get("id")
        deadline = time.monotonic() + timeout
        started = time.monotonic()
        announced = started
        while interaction.get("status") not in TERMINAL_STATUSES:
            if interaction.get("status") not in ("in_progress", None):
                break
            if time.monotonic() > deadline:
                self._cancel(interaction_id, headers)
                raise ProviderError(f"No answer after {timeout:.0f} seconds; the request was cancelled.")
            elapsed = time.monotonic() - started
            time.sleep(3 if elapsed < 30 else 8)
            if time.monotonic() - announced >= 60:
                announced = time.monotonic()
                log(f"Still waiting for the model ({elapsed:.0f}s)")
            try:
                interaction, _ = request_json(
                    "GET", self._url(f"/v1beta/interactions/{interaction_id}"), headers, timeout=60
                )
            except ApiError as exc:
                raise ProviderError(f"Lost track of the request: {exc.message}", exc.status) from None

        result = self._result(interaction, notes)
        if interaction_id:
            try:
                request_json("DELETE", self._url(f"/v1beta/interactions/{interaction_id}"), headers, retries=1)
            except ApiError as exc:
                notes.append(
                    f"The stored interaction {interaction_id} could not be deleted ({exc.message}); "
                    "Google removes it after its retention period."
                )
        return result

    def _run_blocking(self, payload: dict, headers: dict, timeout: float, notes: list) -> dict:
        try:
            interaction, _ = request_json(
                "POST", self._url("/v1beta/interactions"), headers, {**payload, "store": False},
                timeout=timeout, retries=0,
            )
        except ApiError as exc:
            raise ProviderError(exc.message, exc.status) from None
        return self._result(interaction, notes)

    def _cancel(self, interaction_id: str, headers: dict) -> None:
        try:
            request_json("POST", self._url(f"/v1beta/interactions/{interaction_id}/cancel"), headers, {}, retries=0)
        except ApiError:
            pass

    def _result(self, interaction: dict, notes: list) -> dict:
        status = interaction.get("status")
        texts = []
        for step in interaction.get("steps") or []:
            if step.get("type") != "model_output":
                continue
            for part in step.get("content") or []:
                if part.get("type") == "text" and part.get("text"):
                    texts.append(part["text"])
        if not texts:
            for part in interaction.get("outputs") or []:
                if part.get("type") == "text" and part.get("text"):
                    texts.append(part["text"])
        text = "".join(texts)
        if status == "incomplete" and text:
            notes.append("The answer was cut off (status incomplete), usually by the output token limit.")
        elif status != "completed" or not text:
            detail = interaction.get("error") or interaction.get("status_details") or {}
            detail_text = detail.get("message") if isinstance(detail, dict) else str(detail)
            raise ProviderError(
                f"The model returned status {status!r} with {'no text' if not text else 'partial text'}"
                + (f": {detail_text}" if detail_text else ".")
            )
        usage = interaction.get("usage") or {}
        by_modality = {
            entry.get("modality"): entry.get("tokens")
            for entry in usage.get("input_tokens_by_modality") or []
        }
        return {
            "text": text,
            "status": status,
            "notes": notes,
            "usage": {
                "input_tokens": usage.get("total_input_tokens"),
                "output_tokens": usage.get("total_output_tokens"),
                "thought_tokens": usage.get("total_thought_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "video_tokens": by_modality.get("video"),
                "audio_tokens": by_modality.get("audio"),
                "cost": None,
            },
        }
