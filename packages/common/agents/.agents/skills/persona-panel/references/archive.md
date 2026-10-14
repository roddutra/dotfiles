# Archiving a study

Keep two tiers:

1. **Distilled findings in the product repo** (for example `docs/research/<topic>-<yyyy-mm>/README.md`): the headline results, ICP signal, recommendations, decisions and a link to the archive. This is what future agents working on the product will find.
2. **The full study in a separate research repo**, laid out as below. Bulk that can be regenerated is dropped.

## Research repo layout

```
<research-repo>/
  README.md                          index of studies, newest first
  customer-research/
    <yyyy-mm-dd>-<topic>/            date the study finished + short topic slug
      README.md                      study card: question, rounds, method, headline, links
      report/                        the study's visual summary page: the last round's report/, or one
                                     written for every round (source of any published page)
      findings/                      synthesis per round (round-1.md, round-2.md) and the ICP
      inputs/                        briefs, decisions and constraints given to designers
      concepts/<id>/                 each concept's source, once, with its gallery index: a site's folder,
                                     or a files concept's images and PDFs. A url concept has none
      screenshots/<id>--<page>.jpg   one full-page screenshot per page of a site or url concept (snapshot.py)
      panel/round-<n>/               one folder per panel round (archive.py)
        study.json  study-brief.md  key.md  forms.json  runs.json  followups.json  panel-instructions.md
        personas/  prompts/  analysis/  scripts/ (only if the round used one-off scripts)
        report/                      the round's page as the lead left it: index.html, kit.css, kit.js,
                                     standalone.html and anything beside them (references/report-page.md)
        evidence/<run id>/           usability only: steps.jsonl and the screenshots of its steps
        interviews/                  interviews and debriefs: the turn log and full transcript of each
```

Dropped because they regenerate: the site copies, in `panel/sites` or in `sites/` when the study did not browse (from `concepts/` + `key.md`), `panel/materials` (`capture.py`), scratch screenshots, designer verification shots.

What `--concepts` does for each kind of concept:

- **`site`:** copies the folder and screenshots every page.
- **`files`:** copies each image and PDF as `item-<NN>-<its own name>`, numbered in the order `study.json` or the folder gives them, so two files of one name from different folders are both kept. They are their own record, so nothing is screenshotted. When a file of that name is already there with other content, from an earlier archive, it is replaced and a line says so.
- **`url`:** copies nothing, because there is no source. `key.md` records the addresses. The screenshots are taken from the live page at archive time, which may no longer be what the panel saw: archive straight after the runs, and say in the study card when the page was captured. A page that cannot be opened is skipped with a line saying so.

Not archived either:

- `logs/`: the raw harness output of every process, which contains everything a panellist read and wrote. It also holds `earlier-sessions.json`, the only note of the sessions that runs replaced by `init_study.py --force` left with their harnesses: run `launch.py <study> purge-sessions` before deleting the study directory if those sessions should go.
- `.launch.lock`: the study's lock file, which stays with the study.

What travels with a round besides the persona files:

- `analysis/`, whole: `usage.md`, `runs.csv`, `answers.csv` and `lines.csv` with it, and the analysts' copies of the transcripts in `analysis/transcripts/`, in an interview study and in a study that held debriefs. An archived round still analyses.
- `study-brief.md`: what was agreed with the user, hypotheses included.
- `forms.json`: whether each `files` concept is images, PDFs or both. An archive without `--concepts` has no source file to tell them apart, and `analyze.py` needs it for the format caution (`references/method.md`). `archive.py` writes it from the source files while they can be read, else from the study's own copy.
- `report/`: the round's visual summary page, whole. The page carries the notice itself, so its HTML is copied byte for byte. In a usability study its files are scanned for secrets with every other kept file, but a screenshot inside the page cannot be: the page must show none that the evidence rules below leave out.
- `followups.json`: the follow-up questions asked and how each run answered. The answers themselves are in the persona files. `archive.py` refuses a study with a follow-up that is not settled: its persona file may hold what settling will reject, and an archive has no `logs/` to put it back from. It also refuses a study that a launcher has, and holds the study lock while it copies the round, so no follow-up starts under the copy. Of a study it cannot write, as in a read-only sandbox, it keeps a shared lock on `.launch.lock` for as long, which turns every launcher away: one that tries says that something is reading the study, and to try again. A study at rest has that file to share: `init_study.py` makes it and no launcher removes it. Only a study from before that has none, and there `archive.py` refuses a study with a run on record as running and copies any other unprotected (`references/runners.md`, A lead on Codex).

## What the copy reads

A panellist can write under `panel/`, so `archive.py` treats what it finds there as possibly hostile, in a study of any type:

- **Only regular files and folders are read.** A symbolic link at or under a kept name could bring in a file from outside the study. A FIFO, a socket or a device is no file to copy. A file or folder that may not be read or listed is not known to be the study's own. Each refuses the archive and is named with the reason. Put a plain file or folder at the name, or remove it, and archive again.
- **No message repeats a panellist's own text unchecked.** A path under `panel/` is quoted only as far down as it is clean, and the rest is described (`references/usability.md`, Safety).
- **No empty folders.** A folder is archived only as part of the path of a file it holds. One that holds nothing kept, or only `__pycache__` or `.DS_Store`, is left out. The one exception is an empty folder already at the destination that `archive.py` cannot remove: it is named and left (below).
- **An archive that fails while it reads the study leaves the destination as it was.** The round is built in a scratch folder beside the destination, `.<round>.archive-<random>`, and every refusal above happens there. The folder is removed however the archive ends. Only a killed archive leaves one behind, and the next archive to the same place removes it.
- **Archiving again replaces what has the same name and keeps the rest.** A new destination gets the whole round in one rename. Into an earlier archive the files are moved one by one, each of them whole, and folders left empty are removed, the ones an older `archive.py` left too. An empty folder it cannot remove (its parent is read-only, say), or a folder it cannot list to see whether it is empty, is named on stderr with the system's reason and left: the round is archived all the same, the exit code is 0, and no permission is changed. If that is stopped part of the way (an interruption, a kill, a full disk), the destination holds some files of this round and the others as the earlier archive had them: archive again to finish it.

## Usability studies

A usability study has no concepts and no `key.md`, so `--concepts` copies nothing. Its round keeps the other files above, with `analysis/tasks.csv` and `steps.csv`, and each run's evidence, `panel/evidence/<run id>/` as `evidence/<run id>/`. Every step the synthesis cites is found there under the name it was cited by.

| In the archive | How |
|---|---|
| `steps.jsonl` | Byte for byte |
| Screenshots | Every PNG whose name gives its step (`T1-7.png`, `T2-a2-3.png`, and `T1-7b.png` for a further view of step 7 after scrolling) or that a `result` entry names, under its own name. At half size and 256 colours, still a PNG. Without ImageMagick they are copied whole, and a line says so |
| `<screenshot name>.left-out.txt` | One line in place of a screenshot that was left out, saying why. The step log entry stays, so the finding can still be cited |
| `study.json` | Byte for byte, unless it has an `accounts.map`: then each secret is replaced with "(removed from the archive)", identifiers are kept, and a line says so. It still loads |

Screenshots cannot be scanned for text, so three kinds are left out:

- every screenshot of a run whose panellist was given a secret to type (`"signin": "panellist"`)
- the screenshot of a step whose log entry is marked `sensitive`, with every further view of that step
- a file named as a screenshot that is not a PNG image

Never copied:

- anything else in an evidence folder, a link least of all. A line counts what was passed over and names the first few, each after its run id.
- `panel/scratch/`, which holds each panellist's `account.json`
- `accounts/`: the account records, the fingerprint record and what a command of the study wrote when it failed
- saved browser states and `logs/`

Three more refusals, each before anything is copied:

- **A test account is still in force:** its run is not `done`, `limited` or `failed`, or its teardown failed. The archive would describe credentials that work. Finish the run, release it with `launch.py <study> release --runs <ids>`, or fix the teardown.
- **A secret value is in a file the archive would hold.** Every kept file is scanned: persona files, step logs, prompts, `analysis/`, `runs.json`, `followups.json` and the archived `study.json`. Each file is named with its lines and whose secret it was, never the value. A kept file with a secret value in its name, or in the name of a folder above it, is refused too. A folder that holds nothing kept is not archived, so its name goes nowhere. Remove the value from the file or the name, log the edit in `analysis/lead-notes.md`, and archive again.
- **A kept file or an evidence folder cannot be read as the study's own.** The refusal above (What the copy reads) reaches the evidence too: a symbolic link at the evidence root or at a run's evidence folder could bring in a file from outside the study. A kept file or step log that could not be scanned is not known to be clean. Each is named with the reason, and no link is followed. Put a plain file or folder at the name, or remove it, and archive again.

The scan has limits, and the harness's own session records are outside it (`references/usability.md`, Safety). Run `launch.py <study> purge-sessions --yes` once the study is archived.

## Interview studies

An interview study has no concepts, no `key.md` and no persona files, so `--concepts` copies nothing and the round has no `personas/`. It keeps `study.json`, `study-brief.md`, `runs.json`, `prompts/` and:

| In the archive | What it is |
|---|---|
| `interviews/<run id>.jsonl` | The turn log, byte for byte: the one record of what was said and of why an interview stopped |
| `interviews/<run id>.md` | The full transcript: the situation card, and each question with its topic, move and reason. The card is meant to be kept, since the critique was marked against it |
| `analysis/transcripts/<run id>.md` | The analysts' copy: the questions and answers alone |
| `analysis/`, the rest | `qual-<n>.md`, `critique-<n>.md`, `notes.csv`, `critique.csv`, `themes.md`, `quant.md`, `quant.json`, `SYNTHESIS.md`, `quote-check.md`, `checks.md` and `usage.md` |

The paths are the study's own, so an archived round still works with `extract_notes.py`, `analyze.py`, `check_runs.py` and `interview.py <round> quotes`. The three reports those scripts write, `quant.md`, `checks.md` and `quote-check.md`, carry their title and the synthetic panel notice from the script itself in an interview study (`quant.md` is titled with the study's name from `study.json`, not the folder's), so each is the same file in the study and in the round and keeps the line when its script runs again in the round. `usage.md` and the jobs' `<job id>-reply.md` files, which the launcher writes, get the line from `archive.py`. A review or a usability study's `quant.md` and `checks.md` get the line from `archive.py` alone: run either script in an archived round of one and the line is gone until the round is archived again.

Never copied:

- `panel/rooms/` and `interviewer/`: the two sides' working folders, which hold nothing.
- `logs/`: every turn's raw input and output, and any turn log that a fresh start or `init_study.py --force` set aside (`logs/<run id>.interview-<k>.jsonl`, `logs/interviews-<epoch seconds>/`). Those are superseded, never evidence.
- A `synthesis.context_files` file that lies outside `analysis/`, such as a `background.md` beside `study.json`. That is so in a study of any type: only the kept names travel. Copy it into `inputs/` by hand when the writer's summary rests on it. In an archived round the writer is not read as out of date for a file the archive left out.

Two more refusals, each before anything is copied:

- **A turn is in flight:** a side of an interview has an attempt with no end, so a process may still be answering and its answer is not on the turn log. `launch.py <study> stop` settles it and starts nothing. `launch.py <study> resume` goes on with the interview.
- **A launcher is carrying an interview between two turns.** Wait for it to end, or stop it. A study whose launcher was killed is not refused for the mark it left: the interview is archived as its turn log stands.

An interview with no end record does not stop the archive. A line names each one with the state it reads as and how far it got, and `analyze.py` lists it under "Incomplete interviews" and counts it in no table. An interview with turns on record and no transcript is named too: run `interview.py <study> render` and archive again.

Nothing of an interview study is scanned. It has no test accounts, so there is no secret to look for, and a `leak_terms` entry in a question, a card or an answer is for `check_runs.py` to report before the round is archived. Archive only after `interview.py <study> quotes` exits 0, so that `quote-check.md` in the round says every quotation was found.

## Studies that held debriefs

A review or usability study that held debriefs (`references/debriefs.md`) keeps them as an interview study keeps its interviews, at the study's own paths:

| In the archive | What it is |
|---|---|
| `interviews/<run id>.jsonl` | The debrief's turn log, byte for byte |
| `interviews/<run id>.md` | The full transcript, headed "Debrief", with the interviewer's topic, move and reason for each question |
| `analysis/transcripts/<run id>.md` | The analysts' copy, which the analysts' and the writer's briefs name |
| `prompts/interviewer-<run id>.md` | The interviewer's prompt, with the guide |
| `runs.json` | Each debrief's interviewer entry, and on each run what its debrief used |

- **One line says what travels:** "Debriefs: 2 turn logs and 2 transcripts in interviews/, with the analysts' copies in analysis/transcripts/. The interviewers' folders and logs/ stay behind." A debrief with no end record is archived as it stands, and a second line names each with how far it got.
- **A debrief with turns on record and no transcript** travels as its turn log alone. Run `interview.py <study> render` first.
- **Refused while a turn of a debrief is not settled:** "1 turn of this study is not settled (P01-a, the participant's turn): its process may still be answering, and what it answers is not on the turn log yet. Nothing was archived. launch.py `<study>` stop settles it and starts nothing, and interview.py `<study>` debrief --runs `<ids>` goes on with the debrief." The run's persona file is read from a copy until then, and an archive has no `logs/` to put it back from.
- **In a usability study both transcripts are scanned for a test account's secrets** with every other kept file. A review study's are not scanned: `leak_terms` in an answer are yours to find before the round is archived.
- **Never copied:** `interviewer/`, and `logs/` with each turn's raw input and output and any `rejected` file a turn left.
- **An archived round still checks and analyses** with the same commands, and its tables are what they were before the debriefs.

## Synthetic panel notice

Everything archived carries the notice, word for word (`references/communicating.md`), so a file opened on its own is never taken for research with real people.

- **`archive.py` adds it to every markdown file it copies that lacks it:** under the `# ` title the file opens with, or at the very top when it opens with anything else, a `##` or deeper heading included, so a theme or a note that opens a file keeps its fields directly under its heading. A file that has the line anywhere is left alone, so archiving twice changes nothing. The closing line says the same both times: how many markdown files of the round carry the notice, not how many were given it.
- **CSV, JSON and every other kind of file are copied byte for byte,** as is everything `--concepts` copies.
- **The lead adds it to what the script does not write:** under the title of the study card README, of each file in `findings/`, of the product repo's findings README and of the report page (which `report_kit.py <study> init` writes into the starting page). A synthesis copied into `findings/` already has it. Check it survived any editing.

## Steps

1. `archive.py <study-dir> --dest <repo>/customer-research/<date-topic>/panel/round-<n> --concepts` for each round (use `--concepts` once).
2. Write the study card README and copy the synthesis into `findings/`. Each carries the synthetic panel notice under its title.
3. Copy the last round's `panel/round-<n>/report/` to the study's `report/`, or write one page for every round there. A published page's link may be private to an account, so keep the HTML in the repo.
4. Add a line to the repo README index.
5. Mark anything invented for the concepts (placeholder prices, unconfirmed claims) as unconfirmed in the study card, so later readers don't treat it as fact.
6. Check size before committing: `du -sh`. Screenshots at 50% JPEG are about 100 to 700 KB per page; use Git LFS only if a study exceeds ~100 MB.
