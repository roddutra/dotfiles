# Providers

Provider names map to an adapter in `scripts/providers/`. The table in `scripts/settings.py` (`PROVIDERS`) holds each provider's adapter, default endpoint and whether a key is required.

| Provider | Adapter | Default endpoint | Video transport |
|---|---|---|---|
| `gemini` | `gemini` | `https://generativelanguage.googleapis.com` | Upload, then reference by URI |
| `openrouter` | `openai_compat` | `https://openrouter.ai/api/v1` | Inline base64 |
| `openai-compatible` | `openai_compat` | none; set `VIDEO_WATCHER_BASE_URL` | Inline base64 |

Provider facts below were checked against the vendors' documentation in November 2026. They affect limits and estimates, so re-check them when a preflight error or an estimate looks wrong.

## `gemini`

Exercised end to end.

- **Upload**: Files API, resumable, in 32 MB chunks, resumed after a dropped connection. 2 GB per file. Containers: mp4, m4v, mov, webm, mpeg, mpg, avi, flv, wmv, 3gp.
- **Retention**: Google deletes uploads after about 48 hours. The skill records each upload in `~/.video-watcher/remote-files.json`, keyed by endpoint, key and file hash, and reuses it for later calls on the same file after checking it is still there. `--delete-remote` or `remote_files.py delete` removes it sooner.
- **Model call**: Interactions API. Requests run in the background and are polled, so a slow answer survives a dropped connection. Background runs are stored by the API, so the skill deletes the stored interaction once it has the answer. A model that cannot run in the background is called once, blocking, with storage off.
- **Windows, frame rate, resolution**: applied by the API (`--start/--end`, `--fps`, `--resolution`); no local transcode.
- **Token rates** used for estimates: 70 tokens per frame at low or medium resolution, 280 at high, 25 per second of audio, 1 frame per second by default. In testing the estimate landed within about 6 percent of real usage.
- **Limits**: the model's input limit is read from the API (`config.py check` prints it). A 1M-token model holds roughly 3 hours at default resolution, or just under an hour at high.
- **Models**: `list_models.py` returns everything the key can use; the API does not say which accept video. The general-purpose Gemini models do; the specialised ones (image, speech, embedding, live) are not meant for it.

## `openrouter` and `openai-compatible`

Written from OpenRouter's documentation. Not yet exercised against a live endpoint.

- **Request**: chat completions with a `video_url` content part holding a `data:video/...;base64,` URL. Context files and the prompt travel as text parts.
- **Size**: the whole file is read into memory and sent in one request. Capped at 50 MB by default (`--max-inline-mb`). OpenRouter documents no limit of its own; expect the upstream model's limit to apply.
- **No windows**: trim with `prepare.py --start/--end` first. `--fps` and `--resolution` are ignored, with a note in the output.
- **Context check**: skipped, because token rates for video are model-specific. The provider's own error is reported if the request is too large.
- **Models**: on OpenRouter, `list_models.py` lists only models whose input modalities include video.
- **Key**: optional for `openai-compatible`, so a local server without authentication works. Plain `http` is accepted only for localhost.

## Adding a provider

- **Same protocol, different endpoint**: use `openai-compatible` with `VIDEO_WATCHER_BASE_URL`, or add an entry to `PROVIDERS` to give it a name and default endpoint.
- **New protocol**: add a module in `scripts/providers/` implementing the interface described in `scripts/providers/__init__.py`, and register it in `ADAPTERS` there and in `PROVIDERS`.
