"""Runner for the Pi coding agent's headless CLI, `pi -p`.

Every flag and format below was checked against pi 1.1.0 on 13 October 2026, with one working
provider (a ChatGPT subscription login) and no OpenAI-compatible endpoint configured. "Verified"
means seen in a real run, "inferred" means read from Pi's bundled docs or the source in its
binary. Nothing was run on a custom endpoint, so that path is inferred throughout.

Launch (the caller starts the process in workdir and writes the prompt to stdin):

    pi -p --mode text --session-id <uuid> --session-dir <sessions>/--<workdir>--
      --provider <provider> --model <provider>/<id> [--thinking <level>]
      -nc -ns -ne -np --no-themes --no-mcp --no-approve
      --system-prompt "" --append-system-prompt ""
      -e <pi_guard.ts> --panel-guard files|browse
      --tools read,write,edit,grep,find,ls[,bash]

Resume is the same with `--session <id>` in place of `--session-id <uuid>`, from the same
working directory. The model and thinking level are stored in the session, the tools and every
other option are not (verified: a resume without --tools got the default tools back), so
everything is repeated.

What each option is for (all verified unless marked):

- `-p` with the prompt on stdin, and stdin closed. Stdin arrives whole, with nothing read as
  an option, a slash command or an @file. A prompt argument is appended to stdin with no
  separator and fails above 128 KB.
- `--mode text`: stdout is the final reply and nothing else, a provider error is one line on
  stderr and the exit code is 1 for a turn that ended in an error. See "Results" for why not
  `--mode json`.
- `--session-id <uuid>`: the runner picks the id, so the caller records it before the process
  starts. It is never used to resume: where it finds no session it creates a second, empty one
  under the same id and answers from that. `--session <id>` fails instead (SESSION_LOST).
  From another directory `--session` asks on stdout whether to fork the session and reads the
  answer from stdin, where the message is, so the caller must resume in the same directory.
- `--session-dir`: where Pi would keep the session anyway (its sessions folder, then a folder
  named after the working directory), passed so that a `sessionDir` setting or
  PI_CODING_AGENT_SESSION_DIR cannot move it away from where this runner reads and purges.
- `--provider <provider> --model <provider>/<id>`, from the run's "model", `<provider>/<id>`.
  Pi matches a model loosely (`luna` ran `gpt-6-luna`), sends an id it does not know to the
  API as a custom model, and given `--model <provider>/<id>` alone can move to another
  provider that has a model of that name (inferred). So the runner launches only an exact row
  of the model listing, and names the provider apart. A run with no model is refused: Pi would
  use the default model and thinking level of the user's own settings, which no study can pin.
  How Pi reads the two options (its resolveCliModel, read from the source and verified on a
  scratch configuration whose endpoint is a closed port, so with no model call): it finds the
  provider ignoring case, drops one leading `<provider>/` from the model argument, ignoring
  case, and looks for what is left among that provider's models, ignoring case: first as
  `<provider>/<id>`, then as an id. One match is the model. None or several and it matches
  loosely, on any id that contains the text. So `--model <id>` alone picked `foo` for the id
  `custom/foo`, and `bar-turbo` for `bar` beside an id `BAR`. Passing `<provider>/<id>` makes
  what is left exactly the id, whatever it starts with, and the row is the one launched unless
  another row gets in the way. The rule (_clash() below): a listed row `<provider>/<id>` is
  refused, at the plan and at launch, when another listed row has (a) a provider that differs
  from `<provider>` only in case, (b) under the same provider, an id that differs from `<id>`
  only in case, or (c) under the same provider, an id `<x>` such that `<provider>/<x>` equals
  `<id>` ignoring case (`custom/custom/foo` beside `custom/foo`). Every other listed row
  resolves to itself. Pi resolves among all the models it knows and the listing shows those
  of signed-in providers, so a provider with no login whose name differs only in case from a
  listed one is not seen here.
- `--thinking off|minimal|low|medium|high|xhigh|max`: Pi only warns about any other value and
  runs at the user's default level, so the level is validated here and a bad one raises. A
  level the model lacks is clamped by Pi without a message. With no effort set the user's
  default level applies.
- `-nc -ns -ne`: no AGENTS.md or CLAUDE.md (global, working directory and every parent), no
  skills, no extensions (user packages, project extensions, the built-in MCP, sub-agent and
  tool-search extensions). `-np --no-themes --no-mcp` are covered by `-ne` in a headless run
  and are passed to pin them. `--no-approve` ignores the working directory's own `.pi/`.
- `--system-prompt "" --append-system-prompt ""`: keep a global SYSTEM.md or APPEND_SYSTEM.md
  out, which none of the flags above does. Pi's own system prompt stays.
- `-e <pi_guard.ts> --panel-guard files|browse`: the guard extension beside this file. Pi has
  no sandbox and asks for no approval: without the guard its file tools read and write
  anywhere the user can (verified). The guard confines them to the working directory and,
  for a run that may browse, allows the shell tool one agent-browser command at a time; its
  header says exactly what it checks. Pi's file tools rewrite a path before opening it (read
  from the source, each step then verified through the guard): Unicode spaces become spaces,
  one leading "@" is dropped, "~" becomes the home directory or else a file:// URL is decoded,
  and read tries four more spellings of a file that is missing. A guard that checked a path
  Pi then rewrote again was passed by a file:// URL with an encoded no-break space, beside a
  link whose name ends in a space (verified, then fixed: the guard hands over only a path
  that Pi's steps leave as it is). `--panel-guard` is a flag the guard itself defines, so
  a guard that is missing or fails to load stops the launch twice over: Pi refuses an
  extension it cannot load, and without it does not know the flag (verified for a missing
  file, a syntax error and an error thrown while loading).
- `--tools`: an allowlist. `bash` is present only when run["browse"] is true. Images are
  opened with `read`. An unknown tool name is ignored without a message.

Decisions this runner implements:

- The environment is passed through unchanged but for run["browser_env"], the variables by
  which a run that may browse reaches the agent-browser session the caller started for it
  (child_env()). Pi hands its whole environment to the shell tool, so `agent-browser
  <command>` finds that session with no name on the command line. The guard refuses a
  command that sets a variable in front, so a run cannot point a command at another session
  that way. An option can still name one (`--session other`): that is a second, empty
  browser under the same policy, which the caller stops with the first. Pi reads none of the
  variables a host agent sets (verified from inside a Claude Code session).
- PI_CODING_AGENT_DIR is never pointed elsewhere: the login lives there, and the skill does
  not read, store or relay a provider login. The endpoint and its key are configured in Pi.
- No budget cap: Pi has none. The caller's time limit bounds a run.
- Sign-in is per provider, so check() only asks that some model is listed, and
  model_status() answers for one model entry: its exact row in `pi --offline -ne
  --list-models` (which has an "images" column and is read without a model call, with the
  same `-ne` a run gets), then `pi auth check --provider <provider> --json`. That command
  refreshes an expired login, which is how it tells a dead one from a live one, and prints no
  secret. So model_status(), and through it the plan, can make Pi rewrite its own credentials
  file. That is Pi keeping its own login: the runner never reads the file or the login. A
  listed model can still be refused by the API for the account; only a pilot shows.
- A model that takes no images is not an error to Pi: it swaps each image for a line of
  placeholder text (inferred). So the listing is what refuses it for a full-materials study.

Results. `--mode json` prints an event stream that repeats every image a run reads six times
(17.4 MB of stdout for one 2.9 MB sheet, verified), which would put gigabytes in the caller's
logs. So the run prints text, and the facts come from the session file, which holds each
image once and is written as the run goes: `<sessions>/--<workdir>--/<time>_<id>.jsonl`, one
JSON entry per line (Pi's docs/session-format.md). parse_result() finds it by the session id
the caller passes back.

- Session id: the caller's, confirmed by the file. A process that left no file never reached
  its session (a provider with no credential stops there), and reports no id.
- Reply: stdout. The turn finished when the exit code is 0, the last assistant message since
  the last user message has stopReason `stop` or `length` and its text is what stdout holds.
  Without the file (no id passed), exit code 0 with a reply on stdout is taken as finished.
- Errors: a provider error is an assistant message with stopReason `error` and the reason in
  `errorMessage`, which text mode prints on stderr (exit code 1). The message reported is
  this process's stderr, never an older entry of the file. LIMITS below sorts it.
- A killed process (exit code 143) prints nothing; the file keeps every request that finished.
- A resume of a session whose file is gone prints `No session found matching '<id>'` on
  stderr, exit code 1 (verified, also after the file was removed): that is "session_lost".

Usage, scope "session": the sum over the file's assistant messages, `usage` entries and
compaction entries, so it covers earlier processes of the session and one that was killed.
`usage.input` leaves the cached part out, so input_tokens is input + cacheRead + cacheWrite.
Cost is Pi's own figure at list prices, also under a subscription login; a custom model with
no prices in models.json reports 0 (inferred). There is no duration. A request that was in
flight when the process was killed is in no figure.

Sessions are deleted by removing the file: Pi has no command for it and its docs say to.

A sandboxed shell. Nothing was run with Pi's own folder read-only, or with no network, so what
Pi prints there is not known and no pattern for it is here. What follows from the above is
inferred: a session is its file, so shell_check() tests the sessions folder with a write, and a
process that ended well and left no file ran in a session nothing can resume ("session_saved"
false). Pi builds no sandbox of its own.

Not settled: anything on an OpenAI-compatible endpoint (tool calling, whether usage is
reported, the text of its errors); the real text at a usage or rate limit; concurrency above
three runs; compaction in a long run.
"""

from __future__ import annotations

import glob
import json
import os
import re
import tempfile
import time
import uuid

from . import BROWSER_GAPS, child_env, exited, launch_effort, model_facts, result, run_cli, unwritable, usage

CLI = "pi"
EFFORTS = ["off", "minimal", "low", "medium", "high", "xhigh", "max"]
ISOLATION = ["-nc", "-ns", "-ne", "-np", "--no-themes", "--no-mcp", "--no-approve",
             "--system-prompt", "", "--append-system-prompt", ""]
GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pi_guard.ts")
GUARD_FLAG = "--panel-guard"  # defined by the guard itself: Pi refuses it when the guard did not load
FILE_TOOLS = "read,write,edit,grep,find,ls"
LISTING = [CLI, "--offline", "-ne", "--list-models"]
BILLING_ENV = [  # from pi --help and Pi's docs/providers.md
    "PI_CODING_AGENT_DIR", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_OAUTH_TOKEN",
    "ANTHROPIC_BASE_URL", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_BASE_URL",
    "AZURE_OPENAI_RESOURCE_NAME", "OPENROUTER_API_KEY", "XAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
    "CEREBRAS_API_KEY", "DEEPSEEK_API_KEY", "MISTRAL_API_KEY", "TOGETHER_API_KEY", "FIREWORKS_API_KEY",
    "NVIDIA_API_KEY", "BASETEN_API_KEY", "AI_GATEWAY_API_KEY", "OPENCODE_API_KEY", "HF_TOKEN",
    "COPILOT_GITHUB_TOKEN", "RADIUS_API_KEY", "ZAI_API_KEY", "KIMI_API_KEY", "MINIMAX_API_KEY",
    "MOONSHOT_API_KEY", "META_API_KEY", "CLOUDFLARE_API_KEY", "AWS_PROFILE", "AWS_ACCESS_KEY_ID",
    "AWS_BEARER_TOKEN_BEDROCK", "GOOGLE_CLOUD_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "LLAMA_BASE_URL",
    "HTTPS_PROXY", "HTTP_PROXY"]

# An error message that means the provider is turning requests away: a usage limit, a rate
# limit, no quota or credit left, or no capacity. No limit could be triggered, so every text is
# INFERRED from the retry rules and provider adapters in Pi's source. Verified: the shape of a
# provider error (stopReason "error", the reason on stderr, exit code 1 in text mode).
LIMITS = re.compile("|".join([
    r"usage limit",        # INFERRED: "You have hit your ChatGPT usage limit (<plan> plan). Try again in ~<N> min."
    r"rate.?limit",        # INFERRED: rate_limit_exceeded, "Rate limit reached"
    r"too many requests",  # INFERRED
    r"\b429\b",            # INFERRED: an OpenAI-compatible endpoint's message starts with the status
    r"quota",              # INFERRED: insufficient_quota, quota exceeded
    r"available balance",  # INFERRED: no credit left
    r"out of budget",      # INFERRED
    r"overloaded", r"at capacity", r"high demand", r"server_busy",  # INFERRED: capacity refusals
]), re.I)
RESET = re.compile(r"Try again in ~(\d+) min")  # INFERRED: the only reset information Pi passes on
SESSION_LOST = "No session found matching"  # verified: stderr of a resume whose session file is gone
FORKED = "Session found in different project"  # verified: stdout of a resume from another directory, exit code 0
DONE = ("stop", "length")  # stopReason of a turn that finished; "length" is a reply cut at the output limit
NOT_SAID = ("Warning:", "Hint:")  # stderr lines that are not the reason a process failed
UUID = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def capabilities() -> dict:
    return {
        "images_by_path": True,  # for a model whose listing says so: model_status() answers per model
        "image_attach": True,
        "browser": True,
        "budget_cap": False,
        "budget_cap_note": "",
        "effort_levels": list(EFFORTS),
        "resume": True,
        "purge": True,
        "usage": {"tokens": True, "cost": True, "duration": False},
        "default_concurrency": 3,  # the most that was run at once, cleanly. Unmeasured above that
        "provider": "the provider named in each model id, as configured in Pi",
        "billing_env": list(BILLING_ENV),
        "isolation_gaps": [
            "The full path of the working directory is always in the model's context, so folder names "
            "above the panel can leak internal terms.",
            "The path of the Pi installation, which can include the user's home directory name, is always "
            "in the model's context.",
            "Pi's own system prompt stays: it calls the model a coding assistant and asks it to be concise.",
            "The user's Pi settings still apply: the default thinking level for a run that sets no effort, "
            "retries, compaction, and image blocking and resizing.",
            "Pi has no sandbox. A guard extension the runner loads keeps the file tools inside the working "
            "directory, symbolic links followed. It does not see a link put in place between its check and "
            "the tool's use, or a hard link to a file outside. It checks the path as pi 1.1.0 rewrites one "
            "before opening it: a later Pi that rewrites paths another way is not covered until the guard is "
            "checked against it.",
            "Whether a model reads images is taken from Pi's model listing. Where that is wrong, Pi gives "
            "the model a line of placeholder text in place of each image, with no error.",
            "Each session's transcript, every image read included, stays in Pi's sessions folder until it "
            "is purged.",
        ],
        "browse_gaps": [
            *BROWSER_GAPS,
            "With browsing on, the guard's check that a shell command is one agent-browser command is all "
            "that stands between the model and the shell. It reads the command as text, and does not see "
            "what agent-browser then opens or saves.",
            "With browsing on, agent-browser commands that never reach a session are not refused: one of "
            "them lists the names of the user's own browser profiles, and another can attach to a browser "
            "by its debugging port.",
            "With browsing on, shell commands inherit the launcher's whole environment, and Pi tells them "
            "where the session transcript is.",
        ],
    }


# ---------------------------------------------------------------- sessions

def _sessions() -> str:
    home = os.environ.get("PI_CODING_AGENT_DIR") or os.path.join("~", ".pi", "agent")
    return os.path.join(os.path.expanduser(home), "sessions")


def _session_dir(workdir) -> str:
    """Where Pi keeps the sessions of a working directory by default: the folder is named after
    the path, without its leading separator and with every separator and colon as a hyphen."""
    return os.path.join(_sessions(), "--" + re.sub(r"[/\\:]", "-", os.path.realpath(workdir).lstrip("/\\")) + "--")


def _session_files(session_id) -> list[str]:
    if not UUID.fullmatch(session_id or ""):
        return []
    return sorted(glob.glob(os.path.join(glob.escape(_sessions()), "*", f"*_{session_id}.jsonl")))  # oldest first


def _session(session_id) -> dict | None:
    """What a session file records: {"usage", "turn"}, turn being the assistant messages since
    the last user message. None when there is no file. Read best effort: a line that is not a
    whole JSON entry is skipped, as are tool results, which is where the images are."""
    files = _session_files(session_id)
    if not files:
        return None
    total, turn, reported = dict.fromkeys(("input", "output", "cacheRead", "cacheWrite", "cost"), 0), [], False
    try:
        with open(files[-1], errors="replace") as f:
            for line in f:
                if '"role":"toolResult"' in line[:400]:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                message = entry.get("message") if isinstance(entry, dict) else None
                message = message if isinstance(message, dict) else {}
                if message.get("role") == "user":
                    turn = []
                elif message.get("role") == "assistant":
                    turn.append(message)
                used = message.get("usage") if message.get("role") == "assistant" else entry.get("usage")
                if not isinstance(used, dict) or not used.get("totalTokens"):
                    continue  # a request the provider refused reports zeros, which is not a figure
                reported = True
                for key in ("input", "output", "cacheRead", "cacheWrite"):
                    total[key] += used.get(key) or 0
                cost = used.get("cost")
                total["cost"] += (cost.get("total") or 0) if isinstance(cost, dict) else 0
    except OSError:
        return None
    figures = usage(input_tokens=total["input"] + total["cacheRead"] + total["cacheWrite"],
                    output_tokens=total["output"], cached_tokens=total["cacheRead"],
                    cost_usd=total["cost"]) if reported else usage()
    return {"usage": figures, "turn": turn}


# ---------------------------------------------------------------- models

def _listing() -> tuple[dict | None, str]:
    """The models Pi can launch with the options a run gets, {(provider, id): reads images}, and
    why not when the listing cannot be read. No model call."""
    ran = run_cli(LISTING)
    if ran is None:
        return None, f"The {CLI} CLI is not on PATH"
    code, out, err = ran
    rows = [line.split() for line in out.splitlines()]
    head = next((r for r in rows if r[:2] == ["provider", "model"] and "images" in r), None)
    if code != 0 or head is None:
        return None, _said(err) or _said(out) or f"{' '.join(LISTING)} printed no models"
    column = head.index("images")
    return {(r[0], r[1]): r[column] == "yes" for r in rows[rows.index(head) + 1:] if len(r) == len(head)}, ""


def _split(model) -> tuple[str, str]:
    provider, _, name = (model or "").partition("/")
    return (provider, name) if provider and name else ("", "")


def _clash(listed: dict, provider: str, name: str) -> tuple[str, str] | None:
    """The first other listed row that keeps Pi from launching the row (provider, name) when it
    is given `--provider <provider> --model <provider>/<name>`, or None when the row resolves
    to itself. The rule is in the module docstring, under the two options."""
    low = str.lower  # Pi compares with toLowerCase()
    for p, n in sorted(listed):
        if (p, n) != (provider, name) and low(p) == low(provider) and (
                p != provider or low(n) == low(name) or low(f"{p}/{n}") == low(name)):
            return p, n
    return None


def _unlisted(model, listed: dict) -> str | None:
    """Why the model cannot be launched as the exact row of the listing it names, else None."""
    provider, name = _split(model)
    if (provider, name) not in listed:
        same = sorted(n for p, n in listed if p == provider)
        hint = (f"Its models of {provider}: {', '.join(same)}" if same else
                f"It lists no model of a provider called {provider}: is it configured in Pi and signed in? "
                f"Providers listed: {', '.join(sorted({p for p, _ in listed})) or 'none'}")
        return f'{CLI} lists no model "{model}", and would match the name loosely or send it on as it is. {hint}'
    other = _clash(listed, provider, name)
    if other:
        return (f'{CLI} lists "{model}" but cannot be told to launch it: it matches a model name ignoring case '
                f'and drops a leading "<provider>/", so beside the row "{"/".join(other)}" it would launch that '
                "one or match loosely. Rename one of the two in Pi's configuration")
    return None


def model_status(entry: dict) -> dict:
    """The entry's exact row in Pi's model listing, and whether its provider is signed in. known
    is False for a model that is not a row of the listing, and for a row that Pi's own matching
    would take for another one (_clash())."""
    model = entry.get("model")
    provider, name = _split(model)
    if not name:
        return model_facts(known=False, message=(
            f'{CLI} needs "model": "<provider>/<id>", a row of {" ".join(LISTING)}'
            + (f': "{model}" names no provider' if model else
               ": with no model, Pi would use the default model and thinking level of your own Pi settings")))
    listed, why = _listing()
    if listed is None:
        return model_facts(provider=provider, message=f"{CLI} could not list its models: {why}")
    refusal = _unlisted(model, listed)
    if refusal:
        return model_facts(known=False, provider=provider, message=refusal)
    images = listed[provider, name]
    code, out, err = run_cli([CLI, "auth", "check", "--provider", provider, "--json"]) or (1, "", "")
    try:
        auth = json.loads(out)
    except ValueError:
        auth = {}
    auth = auth if isinstance(auth, dict) else {}
    ready = (code == 0 and auth.get("status") == "ready") if auth.get("status") else None
    signed = (f"signed in ({auth.get('authType') or 'login type not given'})" if ready else
              f"whether its provider is signed in could not be asked ({_said(err) or _said(out) or 'no answer'})"
              if ready is None else
              f"its provider {provider} is not signed in ({auth.get('reason') or auth['status']})")
    reads = "reads images" if images else (
        'text only: Pi lists it as taking no images. A model on a custom endpoint that does take them needs '
        '"input": ["text", "image"] in Pi\'s models.json')
    return model_facts(known=True, images=images, signed_in=ready, provider=provider,
                       message=f"{CLI} lists {model}, {signed}, {reads}")


# ---------------------------------------------------------------- commands

def _command(run: dict, workdir, session: list[str], stdin: str, session_id: str, check_model: bool = True) -> dict:
    provider, name = _split(run.get("model"))
    effort = launch_effort(run, EFFORTS)
    if check_model:
        if not name:
            raise ValueError(model_status(run)["message"])
        listed, why = _listing()
        if listed is None:
            raise ValueError(f"could not list its models: {why}")
        refusal = _unlisted(run["model"], listed)
        if refusal:
            raise ValueError(refusal)
    browse = bool(run.get("browse"))
    argv = [CLI, "-p", "--mode", "text", *session, "--session-dir", _session_dir(workdir),
            "--provider", provider, "--model", f"{provider}/{name}", *(["--thinking", effort] if effort else []),
            *ISOLATION, "-e", GUARD, GUARD_FLAG, "browse" if browse else "files",
            "--tools", FILE_TOOLS + (",bash" if browse else "")]
    return {"argv": argv, "stdin": stdin, "env": child_env(run), "session_id": session_id}


def launch_command(run: dict, prompt: str, workdir, limits: dict | None) -> dict:
    session_id = str(uuid.uuid4())
    return _command(run, workdir, ["--session-id", session_id], prompt, session_id)


def resume_command(run: dict, session_id: str, message: str, workdir, limits: dict | None) -> dict:
    if not UUID.fullmatch(session_id or ""):
        raise ValueError(f"not a session id: {session_id!r}")
    return _command(run, workdir, ["--session", session_id], message, session_id)


# ---------------------------------------------------------------- results

def _text(value) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")


def _reasons(text) -> list[str]:
    """What the CLI said went wrong: the lines of its stderr that are not warnings or hints."""
    lines = [line.strip() for line in _text(text).splitlines()]
    return [line for line in lines if line and not line.startswith(NOT_SAID)]


def _said(text) -> str:
    """The reason in one line: every "Error:" line, since a guard that fails to load gives
    two, and otherwise the first line that says anything."""
    reasons = _reasons(text)
    return " ".join(line for line in reasons if line.startswith("Error:")) or next(iter(reasons), "")


def parse_result(stdout, stderr, exit_code, session_id=None) -> dict:
    stdout, stderr = _text(stdout), _text(stderr)
    record = _session(session_id)
    out = result(session_id=session_id if record else None, usage=record["usage"] if record else usage())
    last = record["turn"][-1] if record and record["turn"] else {}
    reply = "".join(b.get("text") or "" for b in last.get("content") or []
                    if isinstance(b, dict) and b.get("type") == "text")
    finished = (last.get("stopReason") in DONE and "".join(reply.split()) == "".join(stdout.split()) if record
                else bool(stdout.strip()))
    if exit_code == 0 and finished and FORKED not in stdout:
        # INFERRED: a reply with no session file under the id the process was given is a session that was not kept
        out.update(outcome="ok", reply=stdout[:-1] if stdout.endswith("\n") else stdout,
                   session_saved=bool(record) if UUID.fullmatch(session_id or "") else None)
        return out
    forked = next((line.strip() for line in stdout.splitlines() if FORKED in line), "")
    reason = last.get("errorMessage") if last.get("stopReason") == "error" else None
    mine = isinstance(reason, str) and reason.strip() and reason.strip().splitlines()[0] in stderr
    text = reason.strip() if mine else "\n".join(_reasons(stderr))  # this process's words, not an older entry's
    out["message"] = ((f"{forked}, so {CLI} asked whether to fork it and stopped" if forked else "")
                      or (text.splitlines()[0] if mine else _said(text))
                      or f"{CLI} ended before finishing its turn ({exited(exit_code)})")
    out["session_lost"] = SESSION_LOST in stderr
    if not forked and not out["session_lost"] and LIMITS.search(text):
        wait = RESET.search(text)
        out.update(outcome="usage_limit", reset_at=round(time.time()) + int(wait.group(1)) * 60 if wait else None)
    return out


# ---------------------------------------------------------------- check and purge

def check() -> dict:
    """Installed, a model listed, the guard loads and every launch and resume option still
    parses. No model call: the launch command with no prompt ends before its first request
    (exit code 0, verified), and the resume command for a session that does not exist ends at
    SESSION_LOST once its options are read. Their sessions go to a folder that is then removed."""
    version = run_cli([CLI, "--version"])
    if version is None:
        return {"ok": False, "message": f"The {CLI} CLI is not on PATH"}
    if version[0] != 0:
        return {"ok": False, "message": version[2] or version[1] or f"{CLI} --version failed"}
    listed, why = _listing()
    if not listed:
        return {"ok": False, "message": why or f"{CLI} lists no models: no provider is configured and signed in"}
    if not os.path.isfile(GUARD):
        return {"ok": False, "message": f"The guard extension is missing ({GUARD}), and no run starts without it"}
    run = {"model": "/".join(sorted(listed)[0]), "effort": EFFORTS[0], "browse": True}
    with tempfile.TemporaryDirectory(prefix="persona-panel-pi-check-") as scratch:
        def probe(session):
            command = _command(run, ".", session, "", "", check_model=False)
            at = command["argv"].index("--session-dir") + 1
            return run_cli(command["argv"][:at] + [scratch] + command["argv"][at + 1:]) or (1, "", "")

        code, out, err = probe(["--session-id", str(uuid.uuid4())])
        if code != 0:
            return {"ok": False, "message": _said(err) or _said(out) or f"{CLI} refused the launch options"}
        code, out, err = probe(["--session", str(uuid.uuid4())])
        if SESSION_LOST not in err:
            return {"ok": False, "message": _said(err) or _said(out) or f"{CLI} refused the resume options"}
    providers = ", ".join(sorted({p for p, _ in listed}))
    return {"ok": True, "message": f"{CLI} {version[1]}, guard loaded, {len(listed)} models listed ({providers})"}


def shell_check() -> dict:
    """Whether Pi's sessions folder can be written (INFERRED: a session is its file, and a run
    that cannot keep one cannot be resumed). The folder of one working directory beneath it
    (_session_dir()) is not tested: this is not told the working directory. Nor is Pi's own
    folder above it, which nothing has shown a run to need. Pi builds no sandbox, and what it
    prints where it cannot reach a provider has not been seen."""
    why = unwritable(_sessions())
    if why:
        return {"ok": False, "message": f"cannot write to {_sessions()}, where it keeps its sessions ({why})"}
    return {"ok": True, "message": ""}


def purge_command(session_id: str, workdir) -> list | None:
    """Removes the session's file, found by id under Pi's sessions folder. None when the id is
    not one this runner made or no file has it. Nothing but a file named for that id is named."""
    found = _session_files(session_id)
    return ["rm", "-f", "--", *found] if found else None
