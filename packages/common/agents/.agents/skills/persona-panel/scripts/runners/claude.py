"""Runner for Claude Code's headless CLI, `claude -p`.

Every flag and format below was checked against claude 2.1.296 with a Claude Max subscription
login on 12 October 2026. "Verified" means seen in a real run, "inferred" means read from the
binary's strings or from old interactive transcripts.

Launch (the caller starts the process in workdir and writes the prompt to stdin):

    claude -p --session-id <uuid> [--model <model>] [--effort <level>] [--max-budget-usd <n>]
      --safe-mode --restricted --strict-mcp-config --disable-slash-commands
      --settings {"includeGitInstructions":false}
      --tools Read,Write,Edit,Glob,Grep[,Bash]
      --allowed-tools Read,Write,Edit,Glob,Grep[,Bash(agent-browser:*)]
      --permission-mode dontAsk --output-format stream-json --verbose

Resume is the same with `--resume <session id>` in place of `--session-id <uuid>`. Nothing
carries over from the first process, so every other option is repeated.

What each option is for (all verified unless marked):

- `-p` with the prompt on stdin. A prompt argument placed after the variadic `--tools` or
  `--allowed-tools` would be read as a tool name, and with a prompt argument the CLI waits
  three seconds for stdin. Stdin avoids both.
- `--session-id <uuid>`: the runner picks the id (uuid4), so the caller can record it before
  the process starts and resume a run that was killed before printing a line. The CLI refuses
  an id that already has a transcript, so every launch gets a new one. `--resume <id>` works
  after SIGTERM and from any directory; tool history and files written survive.
- `--model`: omitted when the run names no model, which leaves the CLI's default. That
  default depends on the account (opus on the tested one), so a study that must be
  reproducible names its model. An unknown name is not caught locally: it fails at the API.
- `--effort low|medium|high|xhigh|max`: the CLI only warns on any other value and carries on
  at its default effort, so the level is validated here and a bad one raises.
- `--max-budget-usd`: enforced under a subscription login too, at list prices. It counts this
  process only, not earlier spend in a resumed session, so the caller passes what is left of
  the run's cap. The check runs after each turn: a run overshoots by up to one turn, which
  capabilities() states in "budget_cap_note" for the plan to print.
- `--safe-mode --restricted`: no CLAUDE.md files (user, project, parent, local), no
  auto-memory, hooks, plugins, skills or user agents. `--restricted` also confines the file
  tools to the working directory, whatever the permission mode. Either flag alone excluded the
  instruction files; `--safe-mode` documents that, `--restricted` was only observed to, so both
  are passed. `--setting-sources ""` is not enough (auto-memory of the enclosing git
  repository still loads), and `--bare` breaks the subscription login.
- `--strict-mcp-config`: no MCP servers from user, project or claude.ai settings.
- `--disable-slash-commands`: removes the built-in skills from the context.
- `--settings {"includeGitInstructions":false}`: removes the git snapshot (branch, user name,
  status, recent commit messages), which is otherwise a leak path for internal terms.
- `--tools` and `--allowed-tools`: the tools that exist, and the ones allowed without asking.
  Bash is present only when run["browse"] is true, and then only `agent-browser` commands
  are allowed; compound commands are checked part by part. Images are opened with Read.
- `--permission-mode dontAsk`: anything not allowed is denied at once, so nothing waits for
  an approval. Denials come back to the model as tool errors.
- `--output-format stream-json --verbose`: one JSON object per line, each with `session_id`,
  ending in a `result` line. `--verbose` is required with stream-json. Plain `json` prints
  only the final object, so a killed process would leave nothing.

Environment. The child gets the caller's environment minus the variables a Claude Code session
sets for its own children: CLAUDECODE, CLAUDE_PID, CLAUDE_EFFORT, AI_AGENT, CLAUDE_AGENT_SDK_*
and every CLAUDE_CODE_* except user configuration (KEEP_ENV). Inherited, they change the
session's entrypoint label and effort, add a scratchpad and an extra agent (verified), and may
leave token refresh to a host process that is not there (inferred). Stripped, a run is the same
from a terminal and from inside Claude Code. CLAUDE_CONFIG_DIR and every ANTHROPIC_* variable
pass through, because they decide which login is used and who is billed. A desktop-hosted
Claude Code session sets ANTHROPIC_BASE_URL (verified), so a plan made inside one reports it.

Results. The result is the last line with "type": "result". Session id: `session_id`, on every
line. Reply: `result`. An error result can say "subtype": "success", so `is_error` decides.
Budget stop: subtype `error_max_budget_usd`, exit code 1, no `result` text, the reason in
`errors`. Any other `is_error` is an error unless it matches USAGE_LIMIT below. No result line
at all means the process was killed or failed before starting (unknown session id, bad flag);
stderr then holds the CLI's message. A resume of a session that has no transcript prints
`No conversation found with session ID: <id>` on stderr and nothing on stdout, exit code 1
(verified, also after the transcript was removed): that is "session_lost".

Usage, scope "session": tokens come from `modelUsage` (summed over models) and cost from
`total_cost_usd`. Both are running totals for the whole session, including resumes and spend
by a process that was killed. The top-level `usage` object covers this process only and is all
zeros on a budget stop, so it is not used, and per-message usage on assistant lines
under-reports. Cost is a list-price figure under a subscription. A killed process reports
nothing; its spend shows up in the next result of the same session. A result with an empty
`modelUsage` (nothing reached a model) reports no tokens or cost.

Sessions are `<projectsDirectory>/<working directory with non-alphanumerics as "-">/<id>.jsonl`,
with a folder of the same name beside it for subagent transcripts. `claude auth status` reports
projectsDirectory. There is no command that deletes one session (`claude purge <dir>` deletes
every session started in a directory, and that directory's memory), so purge_command removes
the transcript itself. Removing it makes the id unknown to `--resume` (verified).

Not settled: the exact headless output at a usage limit; whether `claude auth status` notices
a revoked token; whether the account email can be kept out of context.
"""

from __future__ import annotations

import glob
import json
import os
import re
import uuid

from . import exited, json_lines, last_line, launch_effort, result, run_cli, usage

CLI = "claude"
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
FILE_TOOLS = "Read,Write,Edit,Glob,Grep"
BROWSER_RULE = "Bash(agent-browser:*)"
ISOLATION = ["--safe-mode", "--restricted", "--strict-mcp-config", "--disable-slash-commands",
             "--settings", '{"includeGitInstructions":false}']
OUTPUT = ["--permission-mode", "dontAsk", "--output-format", "stream-json", "--verbose"]

# Session variables a Claude Code host sets for its children, removed from a run's environment.
NESTING_ENV = ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "AI_AGENT")
NESTING_PREFIXES = ("CLAUDE_AGENT_SDK_", "CLAUDE_CODE_")
KEEP_ENV = ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
            "CLAUDE_CODE_USE_FOUNDRY", "CLAUDE_CODE_MAX_OUTPUT_TOKENS")
BILLING_ENV = ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
               "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
               "CLAUDE_CODE_USE_FOUNDRY", "CLAUDE_CONFIG_DIR"]

# How a usage or rate limit shows in an error result. No limit could be triggered, so the
# headless shape is INFERRED from three verified sources: limit hits recorded in interactive
# transcripts (the text, "error": "rate_limit", status 429), the headless shape of another API
# error (an assistant line with "error", then a result with is_error), and the
# rate_limit_event line every headless run prints (seen only with "status": "allowed").
# An error result is a usage limit when any of these holds.
USAGE_LIMIT = {
    "text": re.compile(r"You.ve hit your "),  # INFERRED for headless; verified interactive text
    "status": 429,                            # INFERRED: result api_error_status
    "error": "rate_limit",                    # INFERRED: "error" on the last assistant line
    "event": "rejected",                      # INFERRED: status of the last rate_limit_event
}
# How a resume of a session that is gone starts its one line on stderr.
SESSION_LOST = "No conversation found with session ID"  # verified
# The CLI's reply to a run with no prompt, which check() uses as proof that every option parsed.
NO_PROMPT = "Input must be provided"  # verified
UUID = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def capabilities() -> dict:
    return {
        "images_by_path": True,
        "image_attach": False,
        "browser": True,
        "budget_cap": True,
        "budget_cap_note": "the budget cap is checked after each turn, so a run can go over it by up to one turn",
        "effort_levels": list(EFFORTS),
        "resume": True,
        "purge": True,
        "usage": {"tokens": True, "cost": True, "duration": True},
        "default_concurrency": 6,
        "provider": "Anthropic",
        "billing_env": list(BILLING_ENV),
        "isolation_gaps": [
            "The signed-in account's email address is always in the model's context.",
            "The full path of the working directory, the OS version and today's date are always "
            "in the model's context, so folder names above the panel can leak internal terms.",
            "The model is told whether the working directory is inside a git repository.",
            "With browsing on, the agent-browser CLI can open any file:// path the user can read "
            "and save screenshots outside the working directory.",
            "With browsing on, read-only shell commands inside the working directory (such as "
            "ls) run without being asked for.",
        ],
    }


def _env() -> dict:
    return {k: v for k, v in os.environ.items()
            if k in KEEP_ENV or not (k in NESTING_ENV or k.startswith(NESTING_PREFIXES))}


def _command(run: dict, limits: dict | None, session: list[str], stdin: str, session_id: str) -> dict:
    argv = [CLI, "-p", *session]
    if run.get("model"):
        argv += ["--model", run["model"]]
    effort = launch_effort(run, EFFORTS)
    if effort:
        argv += ["--effort", effort]
    budget = (limits or {}).get("budget_usd")
    if budget is not None:
        amount = f"{budget:.6f}".rstrip("0").rstrip(".")
        if float(amount) <= 0:
            raise ValueError("no budget left for this run")
        argv += ["--max-budget-usd", amount]
    browse = bool(run.get("browse"))
    argv += [*ISOLATION,
             "--tools", FILE_TOOLS + (",Bash" if browse else ""),
             "--allowed-tools", FILE_TOOLS + ("," + BROWSER_RULE if browse else ""),
             *OUTPUT]
    return {"argv": argv, "stdin": stdin, "env": _env(), "session_id": session_id}


def launch_command(run: dict, prompt: str, workdir, limits: dict | None) -> dict:
    session_id = str(uuid.uuid4())
    return _command(run, limits, ["--session-id", session_id], prompt, session_id)


def resume_command(run: dict, session_id: str, message: str, workdir, limits: dict | None) -> dict:
    if not UUID.fullmatch(session_id or ""):
        raise ValueError(f"not a session id: {session_id!r}")
    return _command(run, limits, ["--resume", session_id], message, session_id)


def _usage(res: dict) -> dict:
    ms = res.get("duration_ms")
    out = usage(duration_s=ms / 1000 if isinstance(ms, (int, float)) else None)
    models = [m for m in (res.get("modelUsage") or {}).values() if isinstance(m, dict)]
    if models:
        def total(key):
            return sum(m.get(key) or 0 for m in models)
        cost, cached = res.get("total_cost_usd"), total("cacheReadInputTokens")
        out.update(input_tokens=total("inputTokens") + cached + total("cacheCreationInputTokens"),
                   output_tokens=total("outputTokens"), cached_tokens=cached,
                   cost_usd=cost if isinstance(cost, (int, float)) else total("costUSD"))
    return out


def _usage_limit(res: dict, lines: list[dict]) -> tuple[bool, int | None]:
    """Whether an error result is a usage limit, and when it lifts if the CLI said."""
    assistant = next((x for x in reversed(lines) if x.get("type") == "assistant"), {})
    event = next((x for x in reversed(lines) if x.get("type") == "rate_limit_event"), {})
    info = event.get("rate_limit_info") if isinstance(event.get("rate_limit_info"), dict) else {}
    rejected = info.get("status") == USAGE_LIMIT["event"]
    hit = (rejected or res.get("api_error_status") == USAGE_LIMIT["status"]
           or assistant.get("error") == USAGE_LIMIT["error"]
           or bool(USAGE_LIMIT["text"].match(str(res.get("result") or ""))))
    reset = info.get("resetsAt") if rejected else None
    return hit, reset if isinstance(reset, (int, float)) else None


def parse_result(stdout, stderr, exit_code) -> dict:
    lines = json_lines(stdout)
    out = result(session_id=next((x["session_id"] for x in lines if isinstance(x.get("session_id"), str)), None))
    res = next((x for x in reversed(lines) if x.get("type") == "result"), None)
    if res is None:
        out["message"] = last_line(stderr) or f"{CLI} ended without a result ({exited(exit_code)})"
        out["session_lost"] = SESSION_LOST in out["message"]
        return out
    out["usage"] = _usage(res)
    text = res.get("result") if isinstance(res.get("result"), str) else ""
    errors = [str(e) for e in res.get("errors") or []] if isinstance(res.get("errors"), list) else []
    reason = text or (errors[0] if errors else f"{CLI} reported an error ({exited(exit_code)})")
    if res.get("subtype") == "error_max_budget_usd" or res.get("terminal_reason") == "budget_exhausted":
        out.update(outcome="budget", message=reason)
    elif not res.get("is_error"):
        out.update(outcome="ok", reply=text)
    else:
        limited, reset_at = _usage_limit(res, lines)
        out.update(outcome="usage_limit" if limited else "error", reset_at=reset_at, message=reason)
    return out


def _auth_status(env: dict) -> tuple[int, dict]:
    code, out, _ = run_cli([CLI, "auth", "status"], env) or (1, "", "")
    try:
        status = json.loads(out)
    except ValueError:
        status = {}
    return code, status if isinstance(status, dict) else {}


def check() -> dict:
    """Installed, signed in, and every launch option still parses. No model call: the last step
    runs the launch command with no prompt, which the CLI refuses after reading its options."""
    env = _env()
    version = run_cli([CLI, "--version"], env)
    if version is None:
        return {"ok": False, "message": f"The {CLI} CLI is not on PATH"}
    if version[0] != 0:
        return {"ok": False, "message": version[2] or version[1] or f"{CLI} --version failed"}
    code, status = _auth_status(env)
    if code != 0 or not status.get("loggedIn"):
        said = run_cli([CLI, "auth", "status", "--text"], env) or (1, "", "")
        return {"ok": False, "message": said[1] or said[2] or f"{CLI} auth status: not signed in"}
    probe = launch_command({"model": "default", "effort": EFFORTS[0], "browse": True}, "", ".",
                           {"budget_usd": 0.01})
    _, out, err = run_cli(probe["argv"], env) or (1, "", "")
    if NO_PROMPT not in err + out:
        return {"ok": False, "message": last_line(err) or last_line(out) or f"{CLI} refused the launch options"}
    signed_in = ", ".join(str(status[k]) for k in ("authMethod", "subscriptionType", "apiProvider") if status.get(k))
    return {"ok": True, "message": f"{version[1]}, signed in ({signed_in})"}


def purge_command(session_id: str, workdir) -> list | None:
    """Removes the session's transcript and the folder beside it, found by id under the CLI's
    projects directory. None when the id is not one this runner made or no transcript exists."""
    if not UUID.fullmatch(session_id or ""):
        return None
    projects = _auth_status(_env())[1].get("projectsDirectory")
    found = glob.glob(os.path.join(glob.escape(projects), "*", session_id + ".jsonl")) if projects else []
    return ["rm", "-rf", "--", found[0], found[0][:-len(".jsonl")]] if found else None
