# The visual summary page

Every study ends with one page of its findings that the user can skim, print and pass on. The markdown files stay the full record, and the page points to them. Build it last: after the synthesis, and in an interview study after `interview.py <study> quotes` exits 0. Then send it with the end-of-study message (`references/communicating.md`).

## The kit

`assets/report-kit/` holds a baseline to build from:

- `kit.css`: the styles. Light by default, a dark theme behind a button on the page, and print styles.
- `kit.js`: the helpers under `PP`: tables, charts (drawn with Chart.js), the panel fold, the contents row, tooltips and the screenshot viewer.
- `kit.html`: the kit's documentation page. The rules, the colour tokens, every part with its markup or call, the usual sections of each study type (Recipes), the helpers with their inputs, and the mapping from `study.json` and `runs.json` to `PP.panel`. Open it in a browser: it sits beside `kit.css` and `kit.js`.
- `example-interview.html`, `example-usability.html` and `example-review-specimen.html`: finished pages. The review page is a specimen, with invented data.

Read `kit.html` before writing a page, then the example of the study's type.

## Fixed and free

Whatever the design, the page keeps:

- the synthetic panel notice, word for word, as a paragraph of its own directly under the title
- counts of simulated participants with their base ("3 of 8"), never a percentage of people or "most customers"
- quotations verbatim, each with its run and its exchange or step. In an interview study, only quotations the quote check found
- the evidence against and the limits, shown as plainly as the findings
- a "Go deeper" section naming the markdown files and what each holds

Everything else is yours: colour, type and spacing, which sections appear and in what order, which chart, any part. A project's own design system or brand guidelines win over the kit's look: `kit.html`, "Using a project's own design system", says what to replace and what the helpers still need. Build a part the kit lacks when the study needs one. The reporting rules in `references/communicating.md` hold on the page as in any report.

## Files and commands

The page lives in `<study>/report/`:

- `index.html`: the page you write
- `kit.css` and `kit.js`: copied from the skill, and yours to change
- `standalone.html`: the bundle, which the script writes

`report_kit.py <study> init` makes the folder, copies `kit.css` and `kit.js` into it, and writes a starting `index.html` from the skeleton of the study's type: the notice, the verdict and meta strips, the contents row, and that type's usual sections as headings, each with a comment on what goes there. It never overwrites `index.html`. A kit file that differs from the skill's copy is replaced only with `--force`.

`report_kit.py <study> bundle` writes `standalone.html`: the page with `kit.css` and `kit.js` inlined in one file, to open from disk, print, attach or archive. It refuses a page without the notice. The web fonts and Chart.js still load from their CDNs: without a network the fonts fall back and each chart shows its numbers table instead. Any other relative file the page points to, such as an image, is named: inline it as a `data:` URI before the file goes anywhere else.

Both commands print what to do next. `archive.py` keeps `report/` with the round (`references/archive.md`).

## The data

The page reads no file when it opens. Paste the cut of the data it needs into a script as constants, as the examples do, or write the figures into the markup.

- **`analysis/quant.json`,** the tallies. Review: `leaderboard`, `factors`, `model_scores`, `segments`, `persona_matrix` and `fit`, with `answers`, `lines`, `replicates` and `variants` when their tables were written. Usability: `tasks`, `completion`, `steps`, `stopped` and `stuck_points`. Interview: `themes`, `coverage`, `model_agreement`, `critique` and `quotes`.
- **`analysis/SYNTHESIS.md` and the other markdown files,** the findings, their reasons and the quotations.
- **`study.json` and `runs.json`,** the personas, segments and models and every run's state, for `PP.panel`. Neither goes in as it is: `kit.html`, "PP.panel from the study files", has the mapping, and "Helpers" says what every other helper takes.
- **`analysis/usage.md`,** what was used, for the meta strip and the footer.

In a usability study, `archive.py` scans the page's text for a test account's secrets but cannot read a screenshot inside it. Show none from a run whose panellist was given a secret to type, and none of a step marked sensitive.

## Check it

Bundle, open `standalone.html`, and look at it:

- at desktop width and at phone width (about 390 px): no sideways scroll and no clipped table
- in light and in dark, with the button at the top
- in print preview: every fold opens and the charts print in light colours

A headless browser screenshot at each width is one way to see it. Check every figure against `analysis/quant.md` and every quotation against its source.

## Deliver it

If your harness can publish a web page, publish `index.html` with `kit.css`, `kit.js` and any file it points to beside it, and give the user the link. Otherwise give the user the path of `standalone.html`. Either way, send it with the end-of-study message.
