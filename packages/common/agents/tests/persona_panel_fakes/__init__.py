"""Fake harness CLIs and recorded output for the persona-panel tests. Nothing here calls a model.

    install(bin_dir)        put `claude`, `codex` and `agent-browser` in a directory for PATH
    recorded(cli, name)     the text of <cli>/<name>.jsonl

fake_claude.py and fake_codex.py are the executables; each docstring lists the commands it
answers and how to steer it through the environment. By default one invocation prints one
recorded run. With $FAKE_PANEL set they play whole panellist runs, and analyst and writer jobs,
from a plan, writing their files, waiting at gates and logging events: see panellist.py. fake_agent_browser.py only logs
that it was called. The .jsonl files are output recorded from
the real CLIs on 12 October 2026 (claude 2.1.296, codex-cli 0.162.1), trimmed, with paths
replaced by /study/panel. The fakes print them, and the parsing tests read them directly, so
both follow the real formats. Files named *.inferred.jsonl were not recorded: no usage limit
could be triggered, so they are built from a recorded error with the limit text and fields the
CLI's binary and old sessions point to.

    claude/ok              a run with the isolation flags: init, reply, rate_limit_event, result
    claude/resume-1, -2    the results of two successive resumes of one session
    claude/budget          stopped by --max-budget-usd
    claude/error           an API error (not signed in)
    claude/killed          a run cut off by SIGTERM: no result line
    codex/ok               a run with one shell command
    codex/resume-1, -2     a first turn and a later resume of the same thread (with a warning item)
    codex/budget           stopped by the under-development token budget
    codex/error            a turn the API refused
    codex/killed           a run cut off by SIGTERM: no closing event
    codex/session-file     the token_count event of a session file under $CODEX_HOME/sessions
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIS = ("claude", "codex", "agent-browser")


def install(bin_dir, *clis):
    for cli in clis or CLIS:
        target = Path(bin_dir) / cli
        target.write_text(f"#!{sys.executable}\nimport runpy\n"
                          f"runpy.run_path({str(HERE / f'fake_{cli}.py'.replace('-', '_'))!r}, "
                          "run_name='__main__')\n")
        target.chmod(0o755)


def recorded(cli, name):
    return (HERE / cli / f"{name}.jsonl").read_text()
