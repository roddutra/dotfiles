"""Provider adapters for the video-watcher skill.

An adapter owns one wire protocol: how a video reaches the model, the
transport limits, and the lifecycle of anything it uploads. watch.py drives
every adapter through the same small interface:

  list_models()                      -> [ {id, name, input_token_limit, ...} ]
  model_limits()                     -> {input_tokens, output_tokens} or None
  check_transport(video, options)    -> raises PreflightError when it cannot be sent
  ensure_video(video, options, log)  -> handle (uploads or reuses when needed)
  estimate_video_tokens(seconds, options) -> int or None
  run(handle, request, log)          -> {text, usage, status, notes}
  delete_remote(name)                -> removes an upload, where uploads exist

To add a provider that speaks an existing protocol, add an entry to
settings.PROVIDERS. To add a protocol, add a module here and map it below.
"""

import importlib


class PreflightError(Exception):
    """The request cannot be sent as it stands. Nothing has been charged."""

    def __init__(self, code: str, message: str, options: list | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.options = options or []


class ProviderError(Exception):
    """The provider refused or failed the request."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


ADAPTERS = {
    "gemini": ("providers.gemini", "GeminiAdapter"),
    "openai_compat": ("providers.openai_compat", "OpenAICompatAdapter"),
}


def make_adapter(resolved):
    module_name, class_name = ADAPTERS[resolved.adapter]
    module = importlib.import_module(module_name)
    return getattr(module, class_name)(resolved)
