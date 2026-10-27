---
name: presentation
description: Build presentation slide decks with Slidev that match the current project's brand (colours, fonts, logo, imagery and tone). Load when the user asks for a presentation, deck, slides, pitch, talk, keynote, workshop or PowerPoint-style deck, hands over a brief or content to turn into slides, or wants an existing deck changed, restyled or exported to PDF or PPTX. Covers the brief, brand discovery, scaffolding, writing, visual review and export.
---

# Presentation

Turns a brief into a Slidev deck styled with the current project's brand. Load the `slidev` skill alongside this one as the syntax reference (layouts, animations, components, export flags). Load `mermaid-diagrams` before writing Mermaid fences.

`<skill-dir>` below is the directory containing this file.

## Project layout

One Slidev project per repository holds every deck, so the brand work is done once:

```
presentations/
  BRAND.md            brand decisions and where each came from
  package.json
  styles/index.css    --brand-* tokens and slide styling
  setup/mermaid.ts    diagrams read the same tokens
  global-top.vue      logo and page-number footer
  layouts/            layout overrides
  components/         brand components, if needed
  public/brand/       logo files and licensed fonts
  public/<deck>/      images and video for one deck
  <deck>.md           one kebab-case file per deck
```

Use `presentations/` at the repository root unless the user names another place or the project already has a slides folder. Outside a project, ask where to put it.

## 1. Brief

Take what the user gave, then establish:

- audience, and what they should think or do afterwards
- content and source material
- length in slides or minutes
- delivery: presented live, sent as PDF or PPTX, or shared as a link
- aspect ratio, if not 16:9

Ask only for gaps that would change the deck. State other assumptions in your reply.

## 2. Set up

Reuse `presentations/` if it has a `package.json`. Otherwise:

```bash
mkdir -p presentations
cp -RLn <skill-dir>/template/. presentations/
cd presentations && mv gitignore .gitignore && pnpm install --ignore-workspace
```

- `-L` copies files, not links: the skill directory may be a tree of symlinks.
- `--ignore-workspace` keeps a parent pnpm workspace from absorbing the deck project. Use `npm install` where pnpm is missing.
- Rename `deck.md` to `<deck>.md` for each new deck.

## 3. Brand

If `BRAND.md` is filled in, reuse it. Otherwise look for the brand in this order:

1. Guidelines: `BRAND.md`, `DESIGN.md`, style guides under `brand/` or `docs/`, `_brand.yml`, design-token files, Figma exports.
2. Styling code: Tailwind theme (`tailwind.config.*` or `@theme`), CSS custom properties in the global stylesheet, component-library themes, SCSS variables.
3. Fonts: `next/font` calls, `@font-face` rules, Google Fonts links, font files.
4. Logos: SVGs and favicons in `public/`, `assets/` or `static/`. Prefer SVG. Note light and dark variants.
5. The running product or site, when available: screenshot it for corner radius, shadows, density, imagery and copy tone.
6. Copy tone: landing page, README, marketing content.

Then:

- Fill in `BRAND.md` with every value and its source.
- Set the `--brand-*` tokens in `styles/index.css`. Map colours by role, not by name.
- Check contrast (WCAG AA): 4.5:1 for body text, 3:1 for large text (24px and up). Many brand primaries fail at body size: when it does, set `--brand-primary-text` to a darker mix of the primary that passes, for bold text and small labels.
- List every brand font family under `fonts:` in each deck's headmatter so it loads, and set `fonts.weights` to the weights the fonts ship. A display font with one weight needs headings at that weight, or the browser fakes bold. For licensed font files, copy them to `public/brand/`, add `@font-face` rules to `styles/index.css` and set `fonts.provider: none`.
- Put the logo at `public/brand/logo.svg` for the footer, and a light variant at `public/brand/logo-light.svg` for the cover and end slides, which are dark and hide the footer. With no light variant, remove those two `<img>` tags or swap in a logo that reads on dark.
- Carry the look beyond colour: set `--brand-radius`, then put shadows, imagery treatment and density in `styles/index.css`, `layouts/` or `components/`.

With no brand to find, ask the user for one or propose two or three directions (palette and type pairing) and let them choose. Never pass invented colours off as the project's brand.

## 4. Write

Outline first: one line per slide with its headline and purpose. For decks over about ten slides, or when the brief leaves the story open, show the outline and wait for agreement.

- One idea per slide. The headline states the takeaway ("Churn fell to 2.1%", not "Churn").
- At most six short bullets. Detail goes in speaker notes (`<!-- -->`), which every content slide needs when the deck is presented live.
- Layouts: `cover` to open, `section` between parts, `fact` for a headline number, `two-cols` for comparisons, `end` to close.
- Diagrams: Mermaid fences take the brand colours from `setup/mermaid.ts`. Keep them to about eight nodes, break long labels with `<br/>`, and enlarge with the fence option `{scale: 1.3}`.
- Styling: classes used on more than one slide go in `styles/index.css`. A `<style>` block inside a slide only reaches that slide. Wrap element selectors in `:where()`, as the template does, so classes on the element still win.
- Media: files in `public/<deck>/`, referenced as `/<deck>/file.png`. Use `<SlidevVideo>` for video files and `<Youtube id="..." />` for YouTube.
- Motion: one deck-wide `transition` in the headmatter, `v-click` to build dense slides, `magic-move` for code that changes. Do not vary transitions slide by slide.
- Write the copy in the brand's voice.

## 5. Review

Render the deck and look at every slide before handing it over:

```bash
<skill-dir>/scripts/review.sh presentations/<deck>.md --with-clicks
```

Read each `sheet-N.png` contact sheet. Then open the full-size PNG of every slide with a diagram, custom HTML or anything that looks off: thumbnails hide clipped labels and small misalignments. Fix and re-run until clean. Check for:

- text overflowing the slide, colliding with the footer or clipped
- weak contrast, text too small to read from the back of a room
- inconsistent margins, alignment or heading sizes between slides
- diagrams rendered too small, or Slidev error text in place of a slide
- a missing or distorted logo, and fallback fonts where brand fonts should be

PNGs show a video's first frame only. Check playback in the dev server when it matters.

## 6. Deliver

Tell the user how to present: `pnpm dev <deck>.md` in `presentations/`, then <http://localhost:3030>. The presenter view with notes and timer is at `/presenter`.

Export only what the delivery needs, into `exports/` (git-ignored, as is `dist/`):

- PDF: `pnpm exec slidev export <deck>.md --output exports/<deck>.pdf`
- PPTX with editable text: add `--format pptx-editable`. Mermaid diagrams and other SVGs stay pictures.
- Static site: `pnpm exec slidev build <deck>.md --out dist/<deck>`. Add `--base /<path>/` when it is hosted under a sub-path.

## Gotchas

- `markdown-it` must stay a direct dependency at `^14`. Without it, Slidev's Markdown plugins resolve their peer to version 15 and startup fails with `ERR_PACKAGE_PATH_NOT_EXPORTED ... './lib/token.mjs'`.
- Project files cannot import `@slidev/types` or `@slidev/client`: they are not direct dependencies, so pnpm does not expose them. Use the `$nav` and `$slidev` globals in templates and plain default exports in `setup/`.
- `global-bottom.vue` renders behind the slide, where the opaque background hides it. Keep the footer in `global-top.vue`.
- The built-in `end` layout forces black through scoped styles, so `layouts/end.vue` replaces it. Replace any other built-in layout that fights the brand the same way, rather than escalating selector specificity.
- Mermaid cannot parse `oklch()` and other newer colour functions. Keep the `--brand-*` colours in hex or `rgb()`.
- Slidev renders Mermaid inside a shadow root, so `styles/index.css` cannot reach diagrams. Diagram styling goes in `themeCSS` in `setup/mermaid.ts`.
- Mermaid measures labels at 16px but draws them taller, and wraps them at 120px by default. The template's `setup/mermaid.ts` compensates. Do not set the `fontSize` theme variable, which widens the mismatch and clips labels.
- Export needs Playwright's Chromium, which pnpm's build-script policy skips (the template already lists `playwright-chromium`). `review.sh` installs the browser. Before exporting directly, run `pnpm exec playwright install chromium-headless-shell` if export reports a missing executable.
- `--per-slide` drops click steps, so do not combine it with `--with-clicks`.
- During export, headless Chrome logs `Failed to patch FloatingVue` and Wake Lock errors. They do not affect the output, and `review.sh` filters them.
