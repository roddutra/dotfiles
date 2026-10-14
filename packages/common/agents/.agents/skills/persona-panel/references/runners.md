# Runners, isolation and native mode

A runner is the skill's adapter for one coding agent's headless CLI. `launch.py` starts every panellist run, and every analyst and writer job, through the runner its model entry names. Everything the skill knows about a harness lives in `scripts/runners/`. This document says what a lead needs to choose a runner and trust it. The flags, environment variables, output formats and commands are in each module's docstring (`scripts/runners/<name>.py`), and nowhere else.

## Naming runners in `study.json`

| Key | Meaning |
|---|---|
| `type` | Default `"review"`. `"usability"` is a task-based study of a running product, and `"interview"` a round of discovery interviews, each with keys of its own (Usability and browsing, and Interviews, below) |
| `runner` | The default runner for every model entry and synthesis job that names none |
| `models` | Model entries. A bare string is that model on the study's `runner`, and is its own key. An object is `{"key", "runner", "model", "effort"}` |
| `replicates` | Default 1. Above 1, each run is repeated as `<pid>-<key>-r<n>`. Analysis counts replicates as separate runs and adds "Replicate spread" (`references/method.md`, Replicates and variants) |
| `limits.run` | `{"minutes", "budget_usd"}` for each panellist run, over all its attempts. Default 15 minutes and $2. In a usability study the default minutes come from the tasks: 30 seconds for each step they permit, plus 5 minutes. In an interview study it is each participant's allowance over its whole interview, 15 minutes and $0.50 by default |
| `limits.synthesis` | `minutes` for each analyst and writer job, `budget_usd` as one pool split equally among them. Default 30 minutes and $5. An interview study's critics and themes job share it too |
| `limits.interviewer`, `limits.turn` | Interview only: each interviewer's allowance over its whole interview (default 15 minutes and $1), and the minutes one turn of either side may take (default 3) |
| `limits.followup` | `{"minutes", "budget_usd"}` for each run asked a follow-up question, for each question, apart from its run limits and outside the plan's ceiling. Default 5 minutes and $0.50 |
| `limits.debrief` | `{"minutes", "budget_usd"}` for each of the two sides of a debrief, over all its turns, apart from the run's limits and outside the plan's ceiling. Default 10 minutes and $2.00. One turn has 3 minutes: `limits.turn` is an interview study's key |
| `debrief` | Review and usability only: the guide of the debriefs, `interviewer` (a model entry, no default), `goals`, `topics` and `turns` (Interviews, below) |
| `limits.overrides` | Run limits for one model entry, keyed by model key |
| `runners.<name>.concurrency` | Runs to keep going at once on that runner |
| `synthesis` | `analysts` (1 or 2), `analyst` and `writer` (model entries, no default), `decision_maker` (who the synthesis is for), `context_files` (extra files for the jobs, relative to the study directory; the study brief is refused). An interview study adds `critic`, a model entry with no default, and gives `context_files` to the writer alone |
| `browse` | Whether panellists may open pages with `agent-browser`, on runners that can. Default true for a study of sites. With a `url` concept it is off unless set to true, and a study of `files` concepts alone never browses (Concepts, below). A usability study always browses, and refuses `false` |
| `materials` | Default `"full"`. `"text"` is a text-only pass: page text only, no design factors, no browser (`references/method.md`, Text-only pass) |
| `concepts` | Each is `{"id", "path"}` for a folder with `index.html`, or has a `kind` (Concepts, below) |
| `artefact`, `artefact_plural` | What is reviewed, in a few words: "draft homepage design", "draft homepage designs". The instructions of a study with one concept use the singular, and `init_study.py` refuses one that sets the plural without it |
| `capture.max_pdf_pages`, `capture.pdf_pixels` | Default 20 and 1600: the pages of a PDF that are captured, and the long side of each page image in pixels |
| `capture.desktop` | `[width, height]`, default 1440 x 900: the desktop size pages are captured at, and the window of every browser session a run is given |

Model entry rules:

- `key` is letters and digits only and unique within a study, ignoring case. It names persona files, run ids (`<pid>-<key>`), `limits.overrides` and the model column in the analysis. A model name with other characters needs a key.
- Without `model`, the run uses the harness's own default, which depends on the account. The plan prints `default` for it, and neither the plan, `status` nor `analysis/usage.md` says which model that is. Name the model when the study must be reproducible, or when its tier matters, as on both sides of an interview. The `pi` runner refuses an entry without one.
- `effort` must be one of the runner's levels. `plan` and `run` refuse any other value, because the CLIs themselves only warn or fail at the first model call.
- A study where no entry has a runner is in native mode (below). Mixing the two is refused.
- `type` is a key of the study, not of a model entry.

## Usability and browsing

A usability study (`"type": "usability"`) has these keys in place of `concepts`. `references/usability.md` explains each, and `assets/study.usability.example.json` is a complete study.

| Key | Meaning |
|---|---|
| `product` | Required: the product's name, as the instructions and the briefs give it. `product_phrase` does not stand in for it |
| `target` | `{"base_url", "allow_remote"}`. `base_url` is scheme, host and optional port alone, read strictly (`references/usability.md`, The target), on a local development host: exactly `localhost`, `127.0.0.1` or `[::1]`, or a name ending in `.localhost` or `.test`. `allow_remote: true` permits another host, and then every task is `read_only` and the study has no `accounts` |
| `tasks` | `[{"id", "goal", "start", "steps", "success_check", "read_only"}, ...]`, attempted in the order written. `id` is letters and digits, `start` a path on the target (default `/`), `steps` the step limit (default 25), `success_check` a lead-only command whose exit code is the verdict |
| `accounts` | `{"provision" or "map", "teardown", "reset", "signin"}`: a test account for each run. `signin` is `"session"` (the default: the browser starts signed in from a saved state) or `"panellist"` (the panellist is given the secrets to type) |
| `sequential` | Default false. True runs one panellist at a time across all runners, with `accounts.reset` between runs |

- **A study is one type.** A usability study refuses the keys only a review has (`concepts`, `labels`, `find_the_answer`, `artefact` and the like), `"materials": "text"`, `"browse": false`, every `capture` key but `desktop`, and native mode. A review refuses `target`, `tasks`, `accounts` and `sequential`. Both refuse `interview`.
- **Every run of a usability study browses,** so every model entry needs a runner with a browser. `plan` names one that has none as a problem, and no run starts on it.
- **Any run that may browse** (a usability run, or a review run with `browse` on) gets a browser session the launcher starts and stops ([Browser sessions](#browser-sessions)), and needs the `agent-browser` CLI on PATH: `plan` names its absence as a problem, and `run`, `pilot` and `resume` refuse.
- **A usability study's commands** (`success_check` and the `accounts` commands) are run without a shell, from the study directory, with the run id as the last argument. Whether a command's file exists is checked by `init_study.py`, by `plan` and at every start, not when `study.json` is loaded.

## Interviews

An interview study (`"type": "interview"`) has a guide in place of `concepts` or `tasks`. `references/interviews.md` explains every key, and `assets/study.interview.example.json` is a complete study.

| Key | Meaning |
|---|---|
| `interview` | The guide: `about`, `interviewer` (a model entry, no default), `goals`, `topics`, `turns` (default 30 exchanges) and `situation_card` (default true) |
| `limits.run`, `limits.interviewer`, `limits.turn` | What each participant and each interviewer may use over a whole interview, and the minutes of one turn |
| `synthesis.critic` | The model entry of the jobs that critique the interviewer's questions |

- **What an interview asks of a runner** is what every run asks, many times over: one launch for each side, then a resume with one message for every later turn, each a process of its own under a watchdog, with a final reply and usage. An interview of 30 exchanges is about 60 processes. Nothing is browsed, and no file is read or written.
- **The `interview` capability** says a runner is verified for that. `claude` and `codex` declare it. A capability a runner does not declare reads as false, so `pi` is refused with no change to its module: "pi is not verified for interviews, and an interview is carried turn by turn through its runner. Put the model entry on a runner that is (claude, codex)". The plan lists it under "Problems" for the model key or for `interviewer`, and `run` refuses for the same reason. So is a runner that cannot resume a session: every turn after a side's first is one.
- **The `no_tools` capability** says a runner can start a process with no tool. Both sides of an interview are started that way on a runner that declares it, on every launch and every resume, with no exception for a model. The runner's `no_tools_note` says what that leaves, and the plan prints it under "Tools".
  - **`claude`:** no tool of any kind. A side reads, writes and runs nothing.
  - **`codex`:** no shell, no file or image reading and no network. The CLI has no single switch, so the runner passes eight more, for the shell, image viewing, goals, sleep, the browser, computer use and sub-agents, on top of the three switches every Codex run has ([`codex`](#codex), below). That is as few tools as the CLI allows and not none: a patch tool is still listed, which can write files in the process's own folder (not exercised), where there is nothing, and a clock, three tools that read MCP resources, a tool to wait, tools that ask the user for input and sub-agent tools with the same set stay. Asked to run a command or read a file in its folder, such a session could not (verified on codex-cli 0.162.1).
  - **A runner without it** would keep the file tools a review run has, with only its sandbox and its instructions holding a side to its folder, and the plan says so. No runner that is verified for interviews is in that position.
- **No tools means no access, not no talk of tools.** Asked to read a file, a session with no tools on a vendor's smallest model wrote a made-up tool call and an invented result as plain text (one probe).
- **At most as many interviews are carried at once as the interviewer's runner runs processes at once** (`runners.<name>.concurrency`), and each turn still waits for a slot on its own side's runner. Six interviews at once on `claude` and four on `codex`, and twice those, met no rate limit, usage limit or capacity refusal on 13 October 2026.
- **A runner whose harness turns requests away** stops every interview with a side on it. When that is the interviewer's runner, every interview of the study stops, since all share it.
- **Both runners keep their harness's default system prompt** for an interview too: eight interviews, half of them with it replaced, showed no difference that mattered.
- **The jobs of the synthesis** (analysts, critics, the themes job and the writer) are ordinary jobs: they keep their file tools and work in the study directory.

**Debriefs.** `interview.py <study> debrief` holds an interview with a finished run of a review or usability study, through the same turn loop (`references/debriefs.md`). By runner:

- **`pi` is refused,** for a run and for the interviewer, since it does not declare `interview`. Nothing is recorded. The plan names it under "Debriefs" as "Cannot be debriefed: ... Its runs are reviewed as before, and none of them can be debriefed", which changes neither its exit code nor `run`. The runs of the study's other model entries can be debriefed.
- **Native mode is refused:** "this study is in native mode, and a debrief cannot be held in one: the launcher carries every turn between the interviewer and a run's session, each through a runner".
- **The interviewer is started with no tools,** in an empty folder of its own, as an interview's is.
- **The run's side is its own session, resumed in `panel/` with the tools a run has when it does not browse,** whatever the study: no browser session is started for a turn, and a usability run's test account is gone.
  - **`claude`:** `Read`, `Write`, `Edit`, `Glob` and `Grep`, confined to `panel/`, and no shell. A turn can create or overwrite a file there, and delete or rename none.
  - **`codex`:** its sandboxed shell with no network, writing to `panel/` and `/tmp`. A turn can write, delete and rename there.
- **The launcher puts back what a turn changed** of the run's own persona file and, for a usability run, of its evidence folder, and guards nothing else under `panel/`.
- **On `codex`, which has no budget cap, the time of `limits.debrief` is what bounds a side.**

## Concepts

A concept has an `id` (lead only: it is never shown to a panellist) and one of three kinds. The `id` names a folder in the archive, so it is one part of a file name: no slash, no leading dot or hyphen, no `--`, and unique ignoring case.

| `kind` | Keys | Captured under `panel/materials/concept-<label>/` as |
|---|---|---|
| `site` (default) | `path`: a folder with `index.html` | One folder for each `<page>.html`: sheets, raw screens and `page-text.txt` |
| `url` | `pages`: `[{"name": "index", "url": "https://..."}, ...]`, home page first, or `url` alone for one page | The same folders and files, taken from the live page at capture time |
| `files` | `files`: image and PDF paths in the order to go through them, or `path`: a folder, taken in name order | `item-01`, `item-02`, ...: an image as `image.<type>` (with `part-NN.png` when very tall), a PDF as `page-NN.png` and `page-text.txt` |

- **Page names** of a `url` concept are letters, digits, hyphens and underscores, and the first is `index`. A URL is `http` or `https`, public or on a local host.
- **`states`** (a script run before capture) work on `site` and `url` pages, not on `files`. Each is `{"name", "page", "js"}`, captured to the folder `<page>@<name>`: the name follows the rule for page names, and `page` defaults to `index`.
- **Names that become paths are checked when `study.json` is loaded:** page and state names, concept ids, pinned `labels` (letters and digits), persona ids (no hyphen) and slugs. A persona whose name has no letter from a to z and no digit needs a `"slug"`. `capture.py` also refuses to write or delete anything outside `panel/materials`.
- **Site copies** are in `panel/sites/` only when panellists browse. In every other study (`"browse": false`, a `url` concept without `"browse": true`, a text-only study) they are in `<study>/sites/`, where no panellist can read a page's source.
- **File types:** png, jpg, jpeg, webp and gif images, and pdf. PDFs need Poppler (`pdftoppm`, `pdftotext`): without it `init_study.py` and `capture.py` name it and stop.
- **Kinds can mix** in one study. Labels and review orders are shuffled over all of them.
- **Nothing a panellist reads names a source:** no concept id, path, file name or URL. `key.md` maps them. The one exception is a URL in a study with `"browse": true`.
- **Browsing a `url` concept** needs `"browse": true`. The instructions then give each page's address and tell panellists to submit nothing, and the plan names the hosts. A `files` concept has nothing to open, and the instructions say so when other concepts can be browsed.
- **A text-only study** takes the PDFs of a `files` concept and leaves its images out. A concept of images alone is refused.
- **One concept** makes a study with no ranking and no comparison (`references/method.md`, Single-concept studies). `assets/study.files.example.json` is one, made of files.

## Capabilities

From each runner's `capabilities()`. `launch.py plan` prints the gaps that apply to the study.

| | `claude` | `codex` | `pi` |
|---|---|---|---|
| Harness | Claude Code's headless CLI | The Codex headless CLI | The Pi coding agent's headless CLI |
| Provider that receives the materials | Anthropic | OpenAI | The provider each model id names, as configured in Pi |
| Opens images by path | yes | yes | per model, checked at the plan step |
| Browser (`agent-browser`), through a session the launcher starts | yes | yes | yes |
| Verified for interviews (`interview`) | yes | yes | no: refused at the plan step |
| Starts a process with no tools (`no_tools`), for a side of an interview | yes: none at all | yes: as few as the CLI allows (Interviews, above) | no |
| Budget cap | yes, checked after each turn | no | no |
| Effort levels | low, medium, high, xhigh, max | low, medium, high, xhigh, max | off, minimal, low, medium, high, xhigh, max |
| Resume | yes | yes | yes |
| Purge sessions | yes | yes | yes |
| Usage reported | tokens, cost, duration | tokens only | tokens, cost |
| Default concurrency | 6 | 4 | 3 |
| Checked against | claude 2.1.296, Claude Max subscription, 12 October 2026 | codex-cli 0.162.1, ChatGPT plan, 12 October 2026 | pi 1.1.0, ChatGPT subscription login, 13 October 2026 |

No concurrency default is tested: discovery ran four Claude Code, three Codex and three Pi runs at once without an error, and found no documented cap.

Besides `capabilities()`, a runner answers for one model entry at a time (`model_status()`): whether its harness has the model, whether the model's provider is signed in, whether it reads images and who receives the materials. The plan prints the answer under the entry. `claude` and `codex` cannot tell without a model call, so their runner-wide answers stand.

### `claude`

- **Budget cap.** Enforced under a subscription login too, at list prices. The check runs after each turn, so a run can overshoot its cap by one turn. The plan prints this as a caveat beside the ceiling. The cap counts one process, so the launcher passes what is left of the run's allowance on every attempt.
- **A stopped process reports nothing.** A run stopped at its time limit, or by `stop`, prints no result. `status` and `analysis/usage.md` show that attempt as "not reported (process was stopped)", never as zero. The next result of the same session carries the session's running total, so resuming the run brings the spend in. Until then the launcher cannot count it, and the attempt that resumes the run can be given more budget than is left.
- **Models.** `opus`, `sonnet`, `haiku` and `fable` are accepted aliases. An unknown name fails at the first model call, not at the plan. The default model depends on the account (opus on the tested one).
- **Session id.** The runner chooses it before the process starts, so a run killed before it prints a line can still be resumed.
- **Environment.** A run is the same from a terminal and from inside a Claude Code session: the variables such a session sets for its own children are kept out of the run's environment. The variables that decide which login is used and who is billed pass through, and the plan names any that are set. A desktop-hosted Claude Code session sets one of them, so a plan run from inside one reports it.
- **Sessions.** The CLI has no command that deletes one session, so `purge-sessions` removes the session's transcript itself. It can leave an empty project folder behind.
- **Browsing allows the panellist's `agent-browser` commands and nothing else,** one allow rule for each (`agent-browser open`, `snapshot`, `click` and so on). `agent-browser eval`, `cookies` and `--session other ...` match no rule and are denied before they run, and so is a command with a variable set in front. A line that chains another command to one (`mkdir -p ... && agent-browser ...`) is denied whole, and a panellist that is denied tends to give up on the browser and review from the files. So `init_study.py` makes each run's `panel/scratch/<run id>/`, and the instructions tell panellists to run each command on its own. A run that never browsed says so in its researcher notes: nothing else reports it.

Not switched off for its runs:

- The signed-in account's email address is in the model's context.
- So are the full path of the working directory, the OS version and the date. Folder names above `panel/` can leak internal terms.
- The model is told whether the working directory is inside a git repository.
- With browsing on, what every runner leaves open ([Browser sessions](#browser-sessions)).
- With browsing on, read-only shell commands inside the working directory (such as `ls`) run without an allow rule.
- With browsing on, a rule matches how a command starts, so an option after the command reaches the session (`agent-browser snapshot -i --session other` ran). The session's policy is what refuses the options that matter.

The plan lists the browsing gaps only for a study whose panellists can browse on this runner.

### `codex`

- **No budget cap.** The time limit is what bounds a run, a follow-up question and a side of a debrief. The plan leaves these runs out of the ceiling and labels it an estimate.
- **No cost or duration.** `analysis/usage.md` shows tokens and "not reported" for the rest, and the plan judges these runs by time.
- **Browsing turns the sandbox's network on.** A browser started inside the sandbox dies with each shell call, so the session runs outside it and the run reaches it through a socket, which the sandbox allows only with network access on. That is all or nothing: the run's shell can then reach the internet and the pages under review directly. The temporary directories become read-only for such a run, so it cannot start a browser of its own there.
- **Models.** Without `model`, the run uses the first model of the account's list. An unknown model fails at the first model call. Only the low and medium effort levels were run in discovery.
- **Session id.** Known once the process prints its first line, before any model call. A run killed earlier has no session, and `resume` starts it afresh only when it wrote nothing.
- **Usage after a kill.** Read from the session file, best effort. It can miss the request that was in flight.
- **Sessions.** `purge-sessions` deletes them with the CLI's own delete command.
- **Connected apps, web search and image generation are off,** for every run and job of every study type, since 13 October 2026. Until then a Codex session had the tools of every app connected to the signed-in ChatGPT account, web search and image generation, whatever the runner's other options said: the session's own tool list held 293 tools, about 280 of them one for each action of a connected app, and a panellist could have searched the web for the product under review. The runner now passes `--disable apps`, `-c web_search="disabled"` and `--disable image_generation`, and the tool list shows none of the three (verified on codex-cli 0.162.1). A study run on `codex` before that date may hold answers that drew on the first two: `leak_terms` and `check_runs.py` are what would show it.
- **What a session still has besides its shell** (verified on codex-cli 0.162.1): a script tool whose runtime reaches no file, network or process of its own, and inside it a patch tool that writes files in the working directory, a clock, three tools that read MCP resources, an image viewer and goal tools. Beside it, a tool to wait, tools that ask the user for input, and the sub-agent tools, which the switch for them did not remove.

Not switched off for its runs:

- The user's global instruction file (`~/.codex/AGENTS.md`) is always loaded. Excluding it means redirecting the CLI's home directory, and with it the login, which the skill never handles. Check that file for internal terms and add them to `leak_terms`.
- The whole disk is readable from the sandbox, the home directory included. Only writes are confined, to the working directory and `/tmp` (the working directory alone for a run that may browse). "Read nothing outside `panel/`" is an instruction only.
- A run inside a git repository adds a trust entry for that repository to the user's Codex `config.toml`. Keep the study outside a git repository to avoid it.
- The working directory path, the shell, the date and the timezone are in the model's context.
- Sub-agent tools and their instructions stay available.
- A script tool stays available, with the patch tool, the clock and the MCP resource tools inside it, and so do the tools to wait and to ask the user for input (above). No switch was found that removes them cleanly.
- Commands run in a login shell that sources the user's shell profile. A profile that sets an `AGENT_BROWSER_*` variable would give it back to a browsing run's commands, and the session would restart blank (inferred, not run).
- With browsing on, what every runner leaves open ([Browser sessions](#browser-sessions)), and the network: the run's shell can reach the internet, the pages under review without the browser and its policy, and any Unix socket the user can.
- With browsing on, `agent-browser` commands that never reach a session are not refused. One lists the names of the user's own browser profiles.

The plan lists the browsing gaps only for a study whose panellists can browse on this runner.

### `pi`

Pi reaches many providers, an OpenAI-compatible endpoint among them. Only a ChatGPT subscription login was available when the runner was built: nothing has been run on an OpenAI-compatible endpoint, so tool calling, usage figures and error texts there are untested.

- **Models.** `model` is `<provider>/<id>`, the first two columns of `pi --list-models`, and is required. Pi itself matches a name loosely (`luna` ran `gpt-6-luna`), sends an unknown id to the API as it is, and with no model uses the default of the user's own settings. So the runner launches nothing but an exact row of the listing.
- **Checked for each model entry at the plan step,** without a model call: the model is listed, its provider is signed in, and it reads images. `plan`, `run`, `resume` and a follow-up refuse a model that is not listed, one whose provider's login does not work, and, in a full-materials study, one that reads no images. A text-only model can join a `"materials": "text"` study.
- **A listed model that Pi would take for another is refused too.** Pi matches a model name ignoring case and drops a leading `<provider>/` from it. So a row is refused when another listed row has the same provider and an id that differs only in case, the same provider and an id that is this id without a leading `<provider>/` (`custom/custom/foo` beside `custom/foo`), or a provider name that differs only in case. The refusal names both rows: rename one in Pi's configuration.
- **The sign-in check can refresh Pi's login.** Pi tells a working login from a dead one by refreshing an expired one, so `plan`, a follow-up's `--dry-run` and every command that starts a run can make Pi rewrite its own credentials file. The skill never reads that file or the login.
- **The endpoint and its key are configured in Pi, never in `study.json`.** The skill passes the model id and nothing else.
- **Adding an OpenAI-compatible endpoint:** add a provider to `~/.pi/agent/models.json` with its `baseUrl`, `"api": "openai-completions"`, an `apiKey` and its `models`. Give a model that reads images `"input": ["text", "image"]`: Pi lists a custom model as text only without it, and the plan then refuses it for a full-materials study. Pi's own `docs/models.md` and `docs/custom-provider.md` have the format. A built-in provider needs only `/login <provider>` inside Pi.
- **A provider that a Pi extension adds cannot be used:** runs load no extensions.
- **The guard.** Pi has no sandbox and asks for no approval, so the runner loads a guard extension (`scripts/runners/pi_guard.ts`) into every run. It keeps the file tools inside the working directory, symbolic links followed, and refuses the shell. Pi rewrites a path before it opens it (Unicode spaces, a leading `@`, `~`, a `file://` URL), so the guard takes the same steps, hands Pi the path it checked, and refuses one Pi would rewrite again, as well as any control character in a path. With browsing on it allows one `agent-browser` command at a time: no second command, pipe, redirection, substitution or variable, so a command cannot set the variables that name its session. A refusal goes back to the model as a tool error.
- **No guard, no run.** The launch names a flag only the guard defines, so Pi refuses to start when the guard is missing or fails to load, and the runner's check fails first.
- **No budget cap.** The time limit bounds a run, and the plan labels its ceiling an estimate.
- **Usage** is tokens and a list-price cost, read from Pi's session file, so the finished requests of a stopped run are counted. A custom model with no prices in `models.json` reports a cost of 0, which looks the same as free. There is no duration.
- **Logs hold the reply only.** `logs/<run id>.<attempt>.out` is the final reply, a few hundred bytes. Pi's event stream would repeat every image a run reads six times, so the runner does not ask for it. What a run did is in Pi's session file until `purge-sessions` (`pi --export <file>` renders one).
- **Effort.** Pi drops silently to the nearest level a model has. With no `effort`, the default level of the user's Pi settings applies, so set one.
- **Session id.** The runner chooses it before the process starts. A resume must start in the same directory: moving the study directory breaks it.
- **Concurrency.** Three at once ran cleanly on a hosted provider. A local model server wants `"runners": {"pi": {"concurrency": 1}}`.
- **Sessions.** `purge-sessions` removes the session's file. It can leave an empty folder behind.
- **New models.** Pilot each one and read its file against the materials (`references/method.md`, Models). A listed model can still be refused by the API for the account, and an endpoint's image support is whatever `models.json` says: only the pilot shows either.

Not switched off for its runs:

- The full path of the working directory and of the Pi installation are in the model's context. The second can include the user's home directory name.
- Pi's own system prompt stays: it calls the model a coding assistant and asks it to be concise.
- The user's Pi settings still apply: the default thinking level when a run sets no effort, retries, compaction, image blocking and resizing.
- The guard does not see a link put in place between its check and the tool's use, or a hard link to a file outside. It checks a path as pi 1.1.0 rewrites one before opening it, so check the guard again against a later Pi.
- A model wrongly listed as reading images gets a line of placeholder text in place of each image, with no error.
- Each session's transcript, every image read included, stays in Pi's sessions folder until it is purged.
- With browsing on, what every runner leaves open ([Browser sessions](#browser-sessions)).
- With browsing on, the guard's reading of the command text is all that stands between the model and the shell, and it does not see what `agent-browser` then opens or saves.
- With browsing on, `agent-browser` commands that never reach a session are not refused. One lists the names of the user's own browser profiles, and another can attach to a browser by its debugging port.
- With browsing on, shell commands inherit the launcher's whole environment, and Pi tells them where the session transcript is.

The plan lists the browsing gaps only for a study whose panellists can browse on this runner.

### All runners

- A run is `blocked` when its harness turns the request away: a usage limit, a rate limit or a capacity refusal. The reason in `status` is the harness's own message, which says which one it was.
- In a usability study a harness's message that holds a secret of a test account is neither printed nor kept. The reason then names the attempt's `.err` and `.out` files in `logs/`, which have it (`references/usability.md`, Safety).
- A capacity refusal was seen in a real Codex run ("Selected model is at capacity"): the run became `blocked`, and `resume` finished it later.
- A usage limit could not be triggered on any harness, so how one is recognised is inferred from the binaries and old sessions. If runs end `failed` or `partial` with a limit message as their reason, the limit was not recognised: wait for it to lift, continue with `resume` (partial) or `run` (failed), and report the message so the runner can be fixed.
- Dollar figures under a subscription login are list-price equivalents. They say how much allowance is used, not what is paid.

## Browser sessions

With browsing on, the launcher owns each browser and a panellist only sends it commands. The arrangement is the same on every runner (`scripts/browser_session.py`). Native mode has no launcher and no such session: see Native mode.

- **One session for each attempt.** The attempt's watchdog starts an `agent-browser` session before the CLI and stops it after, however the attempt ends: by itself, at its time limit, on `stop`. A resumed run gets a new session on a blank page, and its resume message says so.
- **The run reaches it through its environment:** three variables for the socket directory, the session name and the action policy. A panellist runs `agent-browser <command>` and names no session.
- **The session's working directory is `panel/`,** because the session, not the run, resolves a relative screenshot path. Its viewport is `capture.desktop`.
- **An action policy inside the session** allows what a visitor does: open an address, go back, forward and reload, list the elements, click, type, select, tick, press keys, hover, scroll, wait, answer a dialog, take a screenshot, read the address and the title. It refuses the rest on every runner: scripts in the page, the page source, cookies, storage, saved browser state, an element's text or value by selector, network requests, the console, new tabs, closing the session, and restarting the browser with other options. The list is in `scripts/browser_session.py`.
- **A run that changes those variables loses its session:** `agent-browser` restarts a session that is reached with other settings, blank and signed out.
- **Other `AGENT_BROWSER_*` variables in your environment are kept out of a run,** except the two that say how a browser starts on this machine (`AGENT_BROWSER_EXECUTABLE_PATH`, `AGENT_BROWSER_ARGS`). An `agent-browser` config file still applies.
- **A session that cannot be started stops its run before the CLI runs:** "could not be started", with the reason, and nothing is marked failed. `logs/<run id>.<attempt>.hooks` has the output.
- **Each session holds about 330 MiB.** The plan multiplies that by the runs that can be in flight at once.
- **In a usability study a session can start signed in.** When the run's test account names a saved browser state, the session loads a private copy of it (`logs/<run id>.<attempt>.state`) and deletes the copy, so no panellist has a file to read (`references/usability.md`, Accounts). A follow-up question to a usability run gets no session.
- **A watchdog that was killed stops nothing.** The next `run`, `resume` or `stop` stops the session it left, and `status` says what was found. `status` shows "browser session up" for a running run.
- **A watchdog killed while the session was still starting** leaves the starting command on record in `logs/<run id>.<attempt>.pid`. The next launcher ends that command first, then stops what it had started. The run "could not be started", and nothing is marked failed.

How a session is stopped, by its watchdog or by a launcher:

- **Stopping never runs `agent-browser`.** Its `close --all` kills whatever process a pid file names when the socket does not answer, and `close` for one session can do the same when it restarts a session (0.38.1). A pid in a file may belong to another process by now.
- **Each session is asked to close through its socket,** the recorded one and any second session a panellist opened in the same socket directory. The system names the process that listens on a socket.
- **A signal goes only to a process that still holds its id under the start identity it was noted with:** the recorded daemon and browser, each listening daemon and the browser it started.
- **The record is not trusted.** A record that is a symbolic link, a FIFO or anything else that is not a regular file of yours, or not what the start wrote, is refused before it is read or waited for: nothing is stopped or removed, and every launcher says so until you have looked and deleted it.
- **Nothing is deleted on the record's word.** The record and the policy are named by the attempt. The socket directory goes only when it holds the session's token, is yours alone and sits directly in the temporary directory. A browser's profile directory goes only when a browser the stop identified named it.
- **What could not be ended or proven stays, and is reported:** on the record under `left` and `kept`, by the launcher that settles the attempt, and by `status`.
- **Not covered:** the browser of a second session whose daemon was killed outright. Nothing leads to it. Find it with `ps` by its `--user-data-dir=<temporary directory>/agent-browser-chrome-...`.

Left open on every runner, and printed by the plan:

- Nothing limits where the browser goes or where it saves a screenshot: any address on the network, any `file://` path the user can read, any path the user can write.
- The element list a panellist acts from is what a screen reader gets. It holds text a visitor cannot see and elements that are off screen. Only the instructions say to judge from the screenshot.
- The browser has a debugging port on this machine. The policy refuses reading cookies and page source, but a run that reached that port could read them.

## What is enforced and what stays an instruction

The launcher enforces, on every runner:

- the working directory: `panel/` for a panellist, the study directory for an analyst or the writer, and in an interview study an empty folder of its own for each side
- in an interview study, the cap of an interview in exchanges, what reaches each side (the words under `SAY` and nothing else for the participant), and the leak gate on every question before it is delivered
- the time limit: SIGTERM to the CLI's process group, `--grace` seconds (default 10) to finish the current write, then SIGKILL
- the prompt: the file in `prompts/` on stdin, with nothing added
- one launcher per study
- what a follow-up question may change: the persona file is copied before the question, and anything but one appended `## Follow-up <n>` section is rejected and the file put back. Until the launcher has settled it, every script reads the copy for scores and progress
- what a turn of a debrief may change, which is nothing: the run's persona file, and a usability run's evidence folder, are copied before each turn, and a file that differs afterwards is put back. Until the turn is settled, every script reads the persona file from the copy
- the synthetic panel notice in an analyst's or the writer's saved output: added when the job left it out, under the `# ` title the file opens with, or at the very top when it opens with anything else
- with browsing on, the browser session of each attempt, and what it refuses ([Browser sessions](#browser-sessions))
- in a usability study, each task's step limit, as the backstop to the panellist's own count and only for the steps its step log shows (a run that logs none is bounded by its time limit), and each run's test account: provisioned before its first attempt and torn down when the run is done, limited or failed

Each run's own watchdog process enforces its time limit, so a killed launcher does not unbound its runs. The watchdog also ends whatever the CLI started and left running, and records when and how the run ended. The next `run`, `resume` or `stop` settles the run from that record, or adopts it while it is still alive. A follow-up question is settled the same way, in recorded steps that a later launcher finishes without deciding again (`scripts/panel_lib.py`, "Settling").

- `--grace` is given to a watchdog when its run starts. A run already going keeps the grace it has.
- `--poll` is how often the launcher looks for runs that have ended and for a request to stop. Time limits do not depend on it.
- `stop` reaches each run through its watchdog, with or without a launcher alive. In a usability study it stops the runs even while a process left by a command of the study holds every other command up, then says so and exits with 1 (`references/usability.md`, Commands).
- A process that starts a session of its own leaves the CLI's process group, and the watchdog cannot end it.
- A watchdog that was itself killed records nothing. The next `run`, `resume` or `stop` kills its CLI's process group if the CLI is still running. If the CLI has gone and a group of its id still has processes, the launcher cannot prove they are the run's: it leaves them alone and names their pids, as does `status` until the run next starts. Check them and stop them yourself. Where no list of processes can be had (no `/proc` and no `ps`), it says that it could not check the group, never that nothing is left.

The harness enforces what it has a switch for:

| | `claude` | `codex` | `pi` |
|---|---|---|---|
| User and project instruction files | excluded | project files excluded, the user's global file loaded | excluded |
| Memory, hooks, plugins, skills, MCP servers | excluded | user config (MCP servers, hooks), the skills list and plugins excluded | skills, extensions and MCP servers excluded |
| Git status and recent commit messages | excluded | none seen in context | none seen in context |
| Reading files | working directory only | whole disk | working directory only, by the guard |
| Writing files | working directory only | working directory and `/tmp`, or the working directory alone when the study browses | working directory only, by the guard |
| Connected apps, web search, image generation | none: no MCP server loads, and no such tool exists | switched off (`--disable apps`, `web_search="disabled"`, `--disable image_generation`) | none: no MCP server loads, and no such tool exists |
| Shell commands | none, or the panellist's `agent-browser` commands when the study browses | any, in a sandbox with no network, or with all of it when the study browses | none, or one `agent-browser` command at a time when the study browses, by the guard |
| A side of an interview, and the interviewer of a debrief | no tool at all | no shell, no file or image reading, no network (Interviews, above) | refused |
| A finished run's turn of a debrief | the file tools in `panel/`, no shell, no browser | its shell in `panel/` and `/tmp`, no network, no browser | refused |
| Something not allowed | denied at once, nothing waits for approval | fails at once, nothing waits for approval | refused at once, nothing waits for approval |

These stay instructions in the run prompt, so keep `leak_terms` and `check_runs.py`:

- Read nothing outside `panel/` (Codex always, Claude Code and Pi when browsing).
- Do not read another persona file. Every persona file is inside `panel/`.
- Write only your own persona file. The launcher cannot prevent it, and detects it: it hashes every persona file when a process starts or ends, and `check_runs.py` reports a file that changed while its own run was not running.
- Ignore background in your context: the account email, the working directory path, Codex's global instruction file, and Pi's coding-assistant prompt.
- In a usability study: decide from the screenshot, stay on the product, and never reveal a secret on screen (`references/usability.md`, Safety).

Analyst and writer jobs work in the study directory and never browse. They can read `key.md`, `study.json` and anything else there. So can the critics and the themes job of an interview study: what keeps an analyst there from the guide, and the writer from a transcript, is its brief.

## System prompt

The `claude` and `codex` runners strip instruction files, memory, skills, hooks and MCP servers, and keep their harness's own default system prompt, the one written for a coding agent. That is deliberate: replacing it was tested on 13 October 2026 and decided the same day.

Both CLIs can replace the prompt, with every tool still working. An A/B of ten panellist runs (five per arm, the same two personas on haiku, sonnet and Codex) showed no difference in persona voice, template discipline, scores or ranking larger than the difference between two runs of the same arm. Scores differed between the arms by a mean of 0.42 a cell, with no direction (+0.07 signed), the same concept ranked first in all ten runs, and nothing broke. The one measurable gain was about 30% fewer input tokens on Codex.

- **Decision (the user, 13 October 2026):** both runners keep the default prompt, because overriding it brought no tangible benefit or difference in the research output. The question is set aside, not closed.
- **The `pi` runner** was not part of the experiment and is unchanged. Pi's own system prompt stays ([`pi`](#pi), above).
- **Before changing this,** read the full record: `docs/specs/persona-panel-expansion.md`, "System prompt override (experiment and decision)", under Discovery. It has what each CLI replaces and still sends, the results, when to revisit, and the arguments and traps for each runner. The option that would replace the prompt, and its trap, are named in each runner's docstring.

## Adding a runner

Add one module, `scripts/runners/<name>.py`. The registry lists the package's modules, so nothing else changes (a module whose name starts with `_` is not a runner). Nothing outside `runners/` may name a harness, a flag, an environment variable, an output format or a session path. Full contracts are in the docstring of `scripts/runners/__init__.py`.

| Function | Contract |
|---|---|
| `capabilities()` | A dict: `images_by_path`, `image_attach`, `browser`, `budget_cap`, `budget_cap_note`, `effort_levels`, `resume`, `purge`, `usage` (`tokens`, `cost`, `duration`), `default_concurrency`, `provider`, `billing_env`, `isolation_gaps`, `browse_gaps`. Three more only on a runner that has them: `interview`, `no_tools` and `no_tools_note` |
| `launch_command(run, prompt, workdir, limits)` | Returns `{"argv", "stdin", "env", "session_id"}`. `run["browse"]` says whether the run may browse, and `run["browser_env"]` is then what its environment needs to reach its session. `run["tools"]` is `"files"` (the default) or `"none"`, for a side of an interview, which only a runner with `no_tools` is given. The prompt is delivered verbatim. `env` is the child's whole environment, or None for unchanged. `session_id` is set when the runner can choose the id before the process starts |
| `resume_command(run, session_id, message, workdir, limits)` | The same shape. Repeats every launch setting: no harness tried so far inherits the tools on resume, and most inherit nothing |
| `parse_result(stdout, stderr, exit_code, session_id=None)` | Returns `{"session_id", "reply", "usage", "outcome", "reset_at", "message", "session_lost", "session_saved", "cannot_run"}`, with `outcome` one of `ok`, `usage_limit`, `budget`, `error`. Never raises on missing or cut-off output. `ok` means the harness finished its turn; the persona file decides whether the run is done. The `session_id` argument is the one the command was built with, for a harness whose output does not name its session |
| `check()` | `{"ok", "message"}`: installed, signed in, and the options the runner passes still parse, with no model call. Asking can make a harness refresh its own login, which the runner must never read or relay |
| `shell_check()` | `{"ok", "message"}`: whether the shell the launcher is in lets the CLI do a run at all, asked after a `check()` that passed. No model call, no network test, every command under a timeout. On failure the message is what the CLI cannot do there, as clauses that each start "cannot", with the system's or the CLI's own words in brackets |
| `purge_command(session_id, workdir)` | The argv that deletes one session, or None |
| `model_status(entry)` | `{"known", "images", "signed_in", "provider", "message"}` for one model entry, with no model call. None means the runner cannot tell, and its `capabilities()` and `check()` stand. `known` or `signed_in` false refuses the launch, and `images` false refuses a full-materials study. Like `check()`, it may make a harness refresh its own login |

Rules for a runner:

- `limits` is what is left of the run's allowance: pass `budget_usd` to a harness that has a cap. The run's watchdog enforces `minutes`.
- Raise `ValueError` for an effort the harness lacks, for a budget of zero or less, and for a model the runner can see the harness does not have.
- Confine a harness that has no sandbox yourself, and make the confinement fail closed: a run that cannot be confined must not start.
- Keep a run's output small. Where the harness's event stream is large, read the facts from its session record instead.
- State in `budget_cap_note` how far a run can pass an enforced cap, as a clause that starts "the budget cap". Leave it empty when the cap is exact or there is none. The plan prints it as a caveat to the ceiling.
- `image_attach` says what the harness can do. No runner attaches images yet, and nothing reads it.
- Declare `interview` only once a launch and many resumes of one session have been run on the real CLI, with a message on each. A runner that does not declare it is refused for both sides of an interview, with no edit.
- Declare `no_tools` only when a process started with `"tools": "none"` has been shown to read no file and run no command, on launch and on resume. Raise `ValueError` for `"none"` with `"browse"`: a browser is a tool. Say in `no_tools_note` whether "no tools" is literally none on the harness and what stays where it is not, as a sentence or two with no subject.
- Map a refusal that will pass (a usage limit, a rate limit, no capacity) to `usage_limit`, and put the harness's own words in `message`: the launcher prints them as the reason.
- Set `session_lost` when the CLI refuses a resume because the session is gone. The launcher then starts the run afresh if it wrote nothing, and otherwise leaves it to the lead. Without it, such a resume reads as a CLI that could not be started, and closes the runner for the command.
- In `shell_check()`, test with `unwritable()` the directory where the harness keeps its sessions, and anything more the CLI needs to run at all, such as a sandbox of its own. Test the folder the sessions go in, not only a configuration directory above it: the `codex` runner tests both, because either can be the one that cannot be written. Refuse only on what is known to stop a run: a test that cannot be made, or that fails in a way nothing has explained, passes.
- Set `cannot_run` when a process's output shows that no run of the CLI can work from that shell, whatever the prompt: a clause that starts "it could not", with the CLI's words in brackets. The launcher then does not retry, and starts nothing more on the runner in the command. Add a pattern only for output that was seen, and mark it verified.
- Set `session_saved` to false when the process ran in a session and the harness holds none of that id, and leave it None when the runner cannot tell. The launcher then says that the run cannot be resumed or asked a follow-up, and refuses both.
- Report usage with a `scope`: `session` when the figures are running totals for the session, `process` when they cover one process. The launcher totals a run with `merge_usage()` and `total_usage()` and never double counts a resumed session.
- Never read, store or relay a provider login.
- List in `isolation_gaps` whatever could not be switched off for any run, in plain words. The plan prints it.
- For a run that may browse, apply `run["browser_env"]` with `child_env()`, let one `agent-browser <command>` through from the run's shell, and add only what the harness needs to reach a socket outside its sandbox. Never put a session name on a command line.
- List in `browse_gaps` what stays open only for a run that may browse, starting from `BROWSER_GAPS`, and leave it empty on a runner with no browser. The plan prints it only when the study's panellists can browse on the runner.
- List in `billing_env` the variables that can change who is billed.

Helpers to reuse from `runners/__init__.py`:

- `usage()`, `result()` and `model_facts()`: return values with every key present
- `json_lines()`: the objects in a JSON-lines stream, skipping half-written lines
- `last_line()`: the CLI's own message at the end of stderr
- `exited()`: the exit code for a message, or "exit code unknown"
- `run_cli()`: run a status command for `check()`
- `unwritable()`: why nothing can be written in a directory, tested with a write that leaves nothing behind. A directory that is not there yet is judged by the nearest one above it that is, and a file where a directory belongs, there or on the way to it, is a reason of its own
- `launch_effort()`: the effort to pass, refusing a level the harness lacks

Before writing the module, settle by experiment what the existing docstrings record: the flags that exclude instructions while the login keeps working, tool restriction, the budget cap, output and session id, resume after a kill, a resume of a session that is gone, the shape of a usage limit, where sessions live, a check without a model call, and what the CLI does in a shell that cannot write its configuration directory or reach its provider. Mark each fact verified or inferred.

The new harness also gets its summary in this document: a column in both tables above and a section under [Capabilities](#capabilities), in plain words. Keep its flags, variables and commands in the module's docstring.

Tests run against fake CLIs, never a model. The pattern is in `packages/common/agents/tests/persona_panel_fakes/`:

- `fake_<cli>.py` stands in for the CLI: it answers the version and login commands and prints recorded output for a headless run. Environment variables steer it (`FAKE_<CLI>` picks the recorded run, `FAKE_PANEL` plays whole runs from a plan, `FAKE_CLI_LOG` records each invocation).
- `<cli>/*.jsonl` is output recorded from the real CLI, trimmed: `ok`, `resume-1`, `resume-2`, `budget`, `error`, `killed`, and what a sandboxed shell made of a run (`claude/unreachable`, `codex/nested`). A shape that could not be recorded is named `*.inferred.jsonl`. For Pi they are entries of its session file, which the fake writes where the runner reads them.
- `install(bin_dir)` puts the fakes on `PATH`. Add the new CLI to `CLIS` in `__init__.py`.
- `RunnerTest` in `tests/test_persona_panel.py` holds the runner contracts: the launch and resume command, and result parsing for each outcome.

## Native mode

The lead starts each run with its own subagent tool and tracks it with `runs.py`. Use it when the lead's harness has subagents and no usable headless CLI, or as a fallback when the launcher cannot start a CLI and no terminal is available.

What it lacks:

- No interview study: the launcher carries every turn between the two sessions, so one is refused when `study.json` is loaded.
- No debrief, for the same reason: `interview.py <study> debrief` refuses a native study.
- No limits: nothing stops a run by time or budget.
- No usage record, and no estimate from a pilot.
- No isolation beyond the run prompt. Subagents inherit the lead's project instructions, and internal terms leaked into reviews in the Sept 2026 study.
- No modification record. `launch.py pilot`, `run` and `resume` refuse a native study.
- No check on follow-up questions: nothing is sent for the lead, limited or put back.
- No browser session started for a run, no action policy and no cleanup. With browsing on, the instructions have each panellist start its own session, `agent-browser --session <run id> ...`, save screenshots to `panel/scratch/<run id>/` by absolute path, and close the session when done. Check for sessions left open with `agent-browser session list`.

Set it up by leaving `runner` out of `study.json` and giving `models` the model names the lead's subagent tool accepts. `launch.py plan` still lists the runs.

| Command | Does |
|---|---|
| `runs.py <study> next --limit 20 --running <ids>` | Prints the prompts that fit in free slots, each with its run id, model and effort |
| `runs.py <study> mark <run> <agent-id>` | Records the subagent's id in `runs.json` |
| `runs.py <study> status` | Each run as done, started or pending, with concepts scored |
| `runs.py <study> resume [<run>]` | A tailored message for each unfinished run, with its recorded agent id |
| `runs.py <study> prompt <run>` | One run's launch prompt, to relaunch a run with no recorded agent |

`next`, `mark` and `resume` refuse a study that has runners.

Running a native panel:

1. **Pilot by hand.** Launch one persona on each model, read the files, fix, then launch the rest.
2. **Launch** each prompt from `next` as a background subagent, with the run's model and the prompt text verbatim. Example, Claude Code: the Agent tool with `run_in_background: true`, `model` from the run, and description `Panel <run id>`.
3. **Record the agent id** with `mark` as soon as each run launches. `runs.json` survives context compaction, so a resume goes to the right agent.
4. **Fill slots** as runs finish: check `status`, then `next` again. Claude Code allows about 20 background subagents at once, which is the default `--limit`.
5. **Resume** after an interruption (usage limit, crash, compaction): send each message from `resume` to its recorded agent. Example, Claude Code: SendMessage. Then run `check_runs.py`: resumed runs sometimes duplicate a section.
6. **Check headroom first.** A session usage limit cut off 10 of 18 runs in the Sept 2026 study. They resumed cleanly.

The synthesis briefs are filled by hand:

- Run `extract_answers.py` and `analyze.py` first. Step 6 of the analyst brief reads their tables, and falls back to counting by hand without them.
- Split the persona files by persona, all models of a persona to one analyst, between one or two analysts.
- Give each analyst `assets/qual-brief.md` with every `<PLACEHOLDER>` replaced. Delete the line of a placeholder that has nothing to say (`<EXTRA_CONTEXT_FILES>`, `<INCOMPLETE_RUNS>`, `<FOLLOWUPS>`). Always delete the `<DEBRIEFS>` line: a native study holds no debrief.
- Replace `<NOTICE>` with the synthetic panel notice, word for word (`references/communicating.md`). Never delete its line.
- When follow-up questions were asked, replace `<FOLLOWUPS>` with the text of `assets/qual-brief-followups.md` or `assets/synthesis-brief-followups.md`, and its `<QUESTIONS>` with one line per question from `followup.py <study> list`: the number, the runs asked and the question. An analyst gets only the questions asked of its own personas. When none was asked, delete the `<FOLLOWUPS>` line.
- Then give one writer `assets/synthesis-brief.md`, filled the same way.
- For a text-only study, replace `<TEXT_ONLY_NOTE>` with the text of `assets/qual-brief-text.md` or `assets/synthesis-brief-text.md`. Otherwise delete its line.
- `<REVIEWED>` is what the panel reviewed: "3 concepts (A, B, C) of draft homepage designs", or for one concept "one draft homepage design (Concept A)".
- A count goes in with its noun, so the sentence agrees: `<PERSONAS>` "1 persona" or "12 personas", `<MODELS>` "2 models (opus, sonnet)", `<RUNS>` "24 runs" or "24 runs, 22 of them complete", `<OWN_PERSONAS>` "persona **P01**" or "personas **P01 to P06**", `<FILES>` "12 files".
- For a study with one concept, replace `<ONE_CONCEPT_NOTE>` with the text of `assets/qual-brief-one.md` or `assets/synthesis-brief-one.md`. Otherwise delete its line.
- For concepts of kind `url` or `files`, replace `<KINDS_NOTE>` with the text of `assets/brief-kinds-url.md` and `assets/brief-kinds-files.md`, each with `<CONCEPTS>` as "Concept B was" or "Concepts B and D were". When the concepts differ in form (a PDF beside a captured page or a screenshot), add `assets/brief-kinds-mixed.md` with `<CONCEPTS>` as "A is a live URL and B is PDF files" and `<EXPOSED>` as "Visual design and Mobile are the factors most exposed". Otherwise delete its line.
- A harness may block a subagent from writing a file that looks like a report. Ask for the document as the reply and save it with `extract_agent_reply.py`, which adds the notice when the reply lacks it: under its `# ` title, or at the very top when it opens with anything else.
- Check that a file a subagent wrote itself has the notice under its title. Nothing else adds it in native mode until `archive.py`.

Follow-up questions are sent by hand too:

1. Run `extract_scores.py <study>` and keep a copy of `analysis/scores.csv`.
2. `followup.py <study> ask --runs <ids>|all --question-file <file>` sends nothing. It prints one message per run, with the subagent id that `runs.py mark` recorded, and records the follow-up in `followups.json` as `sent by hand`. A run with no recorded id cannot be asked. With `--dry-run` it names the runs and records nothing.
3. Send each message, verbatim, to its subagent with the harness's tool for messaging one.
4. Run `extract_scores.py` again and compare with the copy. No script checks what a panellist did to its file, and a follow-up may only append its `## Follow-up <n>` section.

The message is the question inside the frame of `assets/followup-message.md`, the same one a runner sends. There is no `limits.followup` in native mode.

## When the lead's own sandbox blocks the launcher

A harness may run its shell tool in a sandbox. The launcher needs four things from the shell it is started in:

- write access to the study directory, where it records every run and every run writes
- for each runner the study uses, write access to the folder where the CLI keeps its sessions, and for the `codex` CLI to its home above that folder too
- whatever else that CLI needs to run at all: the `codex` CLI builds a sandbox of its own for every run
- network access for the CLIs

`plan` tests the first three, and `run`, `pilot`, `resume` and `followup.py ask` test them again before they start anything. The test makes no model call, leaves nothing behind and adds under a second to the plan. A runner the shell cannot run is shown as `CANNOT BE USED` in place of `ready`, with what it cannot do there and the two ways out, and the command exits with 1. Other runners are judged on their own, and `--allow-missing` goes ahead with them. Network access is not tested, because a proxy or a custom endpoint makes any general test unreliable: a run's own output shows it (below).

The two ways out, which every such refusal names: ask the harness to run the command outside its sandbox, or run `launch.py` from a terminal.

### What was tried

Checked on 13 October 2026 on Linux, with claude 2.1.296 and codex-cli 0.162.1: one text-only study of four runs, two on a `claude` entry and two on a `codex` entry. The runs were made before the tests above existed, when `plan` said "ready" everywhere. The last column is what `plan` says since, checked the same day in the same shells with no model.

| Where `run` was started | What the runs did | `plan` now |
|---|---|---|
| A Claude Code session's shell tool, its sandbox off | 4 done, usage recorded, sessions purged | Both ready |
| A terminal, in a clean login environment | The same | Both ready |
| No terminal: `nohup`, stdin from `/dev/null` | The same | Both ready |
| Codex sandbox, read-only (also the default of a headless Codex session) | Nothing started: `run` was refused in one sentence, for the lock file it could not write | Refuses the study directory and both runners |
| Codex sandbox, `workspace-write` | Codex: the CLI exited before printing anything ("could not be started"). Claude Code: no network, so each run failed after about 3 minutes and its retry after 3 more | Refuses both runners |
| The same, with network access | Codex: the same. Claude Code: 2 of 2 done, and no session saved | Refuses both runners |
| The same, with `~/.codex` and `~/.claude` writable | Claude Code: 2 of 2 done, sessions saved. Codex: each run called the model, had every shell command refused, wrote nothing and was retried, for up to 160,000 input tokens a run | Refuses `codex`, `claude` ready |
| A Codex session as the lead, `run` approved to run outside its sandbox | 4 done, sessions purged | Refused inside the sandbox, in a second real run the same day: the lead then asked for `run` outside it, and all four runs were done |

`run` itself was tried again only in the read-only sandbox, where the lock refusal stops it. In the others its refusal rests on the same test as `plan`'s.

### What a refusal means, and what gets past one

- **The study directory cannot be written.** `plan` names it as a problem, and every command that needs the lock is refused in one sentence naming the lock file. `status` still works. `check_runs.py` prints its table, then one sentence for the file it could not write, and its exit code is what the table says. `extract_scores.py`, `extract_answers.py` and `analyze.py` end with one sentence and exit code 1.
- **A CLI cannot write its configuration directory.** A Claude Code run there completes and saves no session. A Codex CLI there does not start.
- **The `codex` CLI cannot build its sandbox.** This is every Codex run started inside another Codex sandbox: the outer sandbox hides the directory of Codex's own background service, and the CLI will not build a sandbox without it. No writable directory changes that, and the outer sandbox refuses that directory as a writable root.

If a run starts all the same, the launcher has a second line for each case:

- **A CLI that exits with an error before printing anything never ran.** The launcher says "could not be started", with the command and the CLI's message. It records no attempt, marks nothing failed, and starts nothing more on that runner in the command.
- **A run whose output shows that its CLI cannot work from this shell is not retried.** That is a Codex run whose every shell command was refused a sandbox, and a Claude Code run that could not reach its provider after its own retries (about 3 minutes with no network). The run is `failed` with the CLI's words as the reason, its attempt and session stay on record, and nothing more starts on that runner in the command. Recognised from recorded output of the two CLIs. No such output has been seen from `pi`, or from `codex` without a network.
- **A run whose session was not saved says so.** When a process ends, the `claude` and `pi` runners look for its session where the harness keeps them. When there is none the launcher prints "session not saved: this run cannot be resumed or asked a follow-up" once, `status` shows it on the run, `resume` starts the run afresh only if it wrote nothing, and `followup.py` refuses it.

A run whose CLI started, printed output and then failed for any other reason is `failed`, and `run` retries it once. In a usability study the retry, like every start that is not a resume, begins with an empty evidence folder: what the folder held is moved to `logs/<run id>.<attempt>.evidence/` (`references/usability.md`, Running).

The CLI's own output for every attempt is in `logs/<run id>.<attempt>.out` and `.err`. On the `pi` runner that is the final reply alone.

### A lead on Codex

- **Inside the sandbox** (`workspace-write`, with the study in the workspace): `status`, `check_runs.py`, in an interview study `extract_notes.py`, `analyze.py` and `interview.py <study> quotes`, and a first `plan`. `plan` there answers for the sandbox, so it refuses the runners and exits with 1. That is expected, and it is not the plan to confirm: it never says `ready`.
- **Outside the sandbox, `plan` first.** After a `plan` that refuses for the shell, ask for approval to run `launch.py <study> plan` outside the sandbox too, and give the reason: it calls no model, starts nothing, and only there answers for the shell the runs will start from. Go on when that plan shows every runner as `ready`. Without it, a lead started four runs having seen only a plan that refused.
- **Confirm that plan with the user, and say in the session that they agreed.** The approval of `run` may be decided by an automatic reviewer, itself a model. It refused the run while nothing in the session said the user had agreed to the materials going to the providers, and allowed the same run once the session said so.
- **Outside the sandbox, then `launch.py <study> run`.** Ask for approval to run that one command outside the sandbox, and give the reason: the CLIs it starts need the network, their own configuration directories and, for `codex`, a sandbox of their own.
- **A study with no `codex` entry can stay inside,** when the sandbox has network access and the Claude configuration directory is a writable root. `plan` inside then shows `claude` as `ready`, and is the plan to confirm.
- **Use the session's own shell tool, and wait on it.** Given a foreground command of several minutes, the lead reached for another tool it had been configured with, which was refused. If the shell tool hands back before the launcher has ended, do not start the command again: poll `launch.py <study> status` until it says "Launcher: not running".
- **`status` inside the sandbox reports what is on record.** The sandbox cannot see processes outside it. While the launcher runs, `status` there prints "Launcher: running" with the command and process id on record, then one line: this shell cannot see the launcher's processes, and run states are as last recorded. It says nothing of any run's process or browser session and calls no run gone. "Launcher: not running" is reliable there: it comes from the launcher's lock, which every shell sees, not from looking for its process.
- **`stop` goes outside too.** Inside the sandbox it signals nothing and says so, and `run` and `resume` are refused while the launcher has the study. The launcher records the process namespace it runs in beside its process id. A process inside the sandbox that happens to hold that id, even under the same start time, is not taken for the launcher: `status` still says that it cannot see the launcher's processes, and `stop` still signals nothing.
- **After a launcher that was killed, its runs go on where the sandbox cannot see them, and every shell can tell.** The launcher's lock is free then. Each run's watchdog holds a lock of its own for as long as it lives, on `logs/<run id>.<attempt>.lock`, and a shell sees a lock whatever processes it sees. `status` inside the sandbox prints "Launcher: not running", shows each run still at work with no "process alive", "process gone" or browser session, and prints the same line: this shell cannot see the launcher's processes, and run states are as last recorded.
- **While such a run is at work, every command that takes the study is refused there, and changes nothing.** `stop`, `run`, `pilot`, `resume`, `check`, `release`, `purge-sessions --yes`, `followup.py ask`, `init_study.py --force` and `archive.py` exit with 1, name the runs they cannot see, settle and signal nothing, and start no second copy of a run. `followup.py list` lists and settles nothing. Run the command outside the sandbox: the launcher there adopts the live runs and settles the ones that ended.
- **In a read-only sandbox the lock file is refused first, and `archive.py` is refused for the runs.** Where the sandbox shows the study read-only, a command that needs the lock is refused in one sentence naming the lock file, whatever the runs are doing ([above](#what-a-refusal-means-and-what-gets-past-one)). `archive.py` goes on without the launcher's lock for a study it cannot write, which is how a round that was archived read-only is archived again. It keeps a shared lock on `.launch.lock` instead, from before it looks at the study until the round is copied, which a shell that only reads can do. Under it, it asks each watchdog's lock, so it too exits with 1 and names the runs it cannot see, and archives nothing.
- **While `archive.py` copies a study it cannot write, no launcher is given the study.** Its shared lock turns every launcher away, so none can start a run under the copy. A launcher command outside the sandbox waits 5 seconds for the lock, then exits with 1 and says that something is reading the study, and to try again once it has finished. It has started and changed nothing.
- **A study at rest keeps its `.launch.lock`, so a read-only shell can lock it.** `init_study.py` makes the file, empty, and a launcher that ends empties it and leaves it. No command removes it, so do not delete it. "Launcher: not running" is what `status` says of it between launchers, and only a launcher that was killed leaves one for the next to report as stale.
- **One case is not protected: a study from before the lock file was kept.** It has no `.launch.lock` until a launcher command has taken it once from a shell that can write it, and a read-only shell cannot make one. `archive.py` refuses that study with a run on record as running, saying that it cannot be protected from a launcher while it is copied: archive that one outside the sandbox. Any other it copies as it is, with nothing to keep a first launcher from starting during the copy, so start none on that study until the archive has finished.
- **A run that has ended holds nothing up.** Its watchdog let go of its lock when it ended, so every shell knows. `status` shows it as "process gone", inside the sandbox too. Once no run is still at work out of sight, the next `stop`, `run` or `resume` settles it from its end record, from whichever shell it is run.
- **A launcher started inside the sandbox takes its runs with it when it is killed, and the next command settles them.** The sandbox ends with its command, and every process in it. The runs leave no end record, but their locks are free, so `status` outside shows them as "process gone" and the next `stop`, `run` or `resume` from any shell settles them as runs whose watchdog was killed. Their process ids were the sandbox's own and name nothing outside it, so that launcher looks none of them up, signals nothing, and adds to each run's reason that "its CLI could not be checked from this shell because it ran in another process namespace". That covers the daemon and the browser on record for the run's browser session: a session still answering at its socket is asked to close there, and no process is signalled under either id. Nothing has to be edited by hand.
- **A sandbox that stays open keeps its runs.** If the launcher was killed inside a sandbox that goes on, its runs are still at work in it, and the shell outside is then the one that cannot see them: `status` and the refusals there are as above. They end when the sandbox does, and any shell settles them then.
- **A command of a usability study is treated the same way.** A provision, teardown, reset or success check that was running when its launcher was killed holds a lock of its own, on `accounts/command.lock`, and its record names the process namespace it was started in. From the other side of the sandbox the next launcher command looks up and signals nothing under the recorded process id, never clears the record by itself, starts no command and exits with 1: run the launcher from the shell that started the command. With the lock held it says that the command is running where this shell cannot look. With the lock free it says that the command has probably ended, which it cannot check: a process that closed the lock file holds no lock. This is the one place where a study waits for the lead after a sandbox has ended: the command ended with the sandbox, no shell is left that can look, and the message says to delete `accounts/command.running` and `accounts/command.lock` and run the launcher again (`references/usability.md`, Commands).
- **When a run's reason has that note, look where the run was started.** A watchdog that was killed can leave its CLI running. A launcher in the shell that started the run ends that CLI. A launcher in any other shell cannot look for it, and the note says so. Nothing is left when the sandbox the run was in has ended. Otherwise look for the CLI with `ps` in the shell that started it, and stop it there.
- **The note about another process namespace is Linux only.** macOS names none, so neither a watchdog nor a launcher records one there. A run whose watchdog was killed is looked for by its process ids, as it always was, and so is the launcher that a lock file names. A lock file written before launchers recorded a namespace is read the same way. The locks are the same on both.

`status`, `plan`, `run`, `resume` and `stop` were checked on 13 October 2026 inside `codex sandbox`, `workspace-write` and read-only, with no model, against a launcher running outside it on fake CLIs. The same day, with that launcher killed and its runs alive: `status`, `stop`, `run`, `resume`, `init_study.py --force` and `followup.py list` inside `workspace-write`, then `status` and `stop` outside it, which adopted both runs and stopped them. With its runs ended instead: `status` and `stop` inside, which settled both. A launcher started inside `codex sandbox` and killed there was checked too: `status`, `stop` and `resume` outside, which settled both runs and then continued them. So was one killed inside a sandbox that stayed open: `status` and `stop` outside, refused until the sandbox had ended. `archive.py` was checked the same day inside `codex sandbox`, `workspace-write` with only its working directory writable and the study read-only outside it: refused for the launcher while that ran, and for the runs it could not see once the launcher was killed, with nothing archived. The shared lock of `archive.py` and the lock of a command were checked the same day in a `bwrap` sandbox with a process namespace of its own, on fake CLIs. With the study bound read-only: `archive.py` inside was refused for a run alive outside, and while it copied a study at rest, one that a killed launcher had left and one whose launcher had ended by itself, a launcher command outside waited 5 seconds and was refused for the reader, then `stop` outside had the study at once after the archive was interrupted. With the study writable: a launcher command on the other side of the sandbox from a provision command, in both directions, was refused while the command lived, and again once it had ended and left a worker that held no lock, with the record kept and nothing signalled or started. With the command inside a sandbox that had then ended, `run` outside was refused until the record was deleted, and then ran `teardown` before it provisioned again.

Not tested:

- macOS, for the locks of the watchdogs: they are plain `flock`, which macOS has, and none of the above was run there
- a process inside the sandbox that holds the launcher's process id under the same start time: no sandbox was made to produce one. The automated tests cover it with a lock file edited to name a live process and another namespace
- a command of a usability study left on the other side of `codex sandbox`, and `archive.py` there while a launcher starts outside it: both were checked under `bwrap` only, as above
- an interactive Codex session, where the same request goes to the user as an approval prompt
- full access mode: with no model, the `codex` CLI could build its sandbox under it, and no run was made
- `pilot`, `resume`, `followup.py ask`, `purge-sessions --yes` and the analyst and writer jobs from a Codex lead, through an approval. Each starts a CLI or writes to a harness's own folders as `run` does, so expect them to need the same approval. The other way out was run on 14 October 2026: a lead in `workspace-write`, with no approval to ask for, gave the user each launcher command to run from a terminal (`plan`, `pilot`, `plan` again, `run` and the four job roles of an interview study), read what each printed, and finished a four-interview study and its analysis
- macOS, where Codex's sandbox is a different one, and the `pi` runner in any sandbox: its test of the shell is inferred

With no way to run a command outside the sandbox and no terminal, native mode is the fallback ([Native mode](#native-mode)). The lead can always read `launch.py <study> status`, `runs.json` and the persona files.

## Running `launch.py` from a terminal

No agent is needed. From the skill's `scripts/` directory:

```
python3 launch.py <study> plan
python3 launch.py <study> pilot
python3 launch.py <study> run
python3 launch.py <study> status        # from a second terminal
python3 launch.py <study> resume
```

- Ctrl-C stops the runs cleanly and leaves them resumable. A second Ctrl-C skips the grace period.
- Closing the terminal does the same, unless the launcher was started under `nohup`: it leaves a hang-up signal that is already ignored alone, and carries on. A terminal multiplexer works too.
- No terminal is needed either. Under `nohup` with stdin from `/dev/null`, as a scheduled job starts a command, a whole panel ran to the end (13 October 2026).
- Exit code 0 means every run the command covered is done.
