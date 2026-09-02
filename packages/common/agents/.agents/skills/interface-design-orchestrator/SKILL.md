---
name: interface-design-orchestrator
description: Manual-only workflow for distinctive interface design from exploration through production delivery. Invoke only when the user explicitly names interface-design-orchestrator or uses the harness's manual skill invocation syntax. It can design, redesign, refactor, improve, polish, or explore web pages, application views, dashboards, admin interfaces, components, prototypes, mockups, and standalone HTML artifacts.
disable-model-invocation: true
---

# Interface Design Orchestrator

Create intentional interfaces through separate discovery, direction, implementation, criticism, and polish stages. Own the workflow. Use any available frontend or interface-polish skills for detailed design guidance rather than duplicating them here.
This skill is manual-only. Do not invoke it autonomously based on a related interface request. The frontmatter flag enforces this in harnesses that support it; this instruction is the fallback in harnesses that do not.


## Start with capabilities

Before choosing a workflow, identify which capabilities the current harness provides:

- Structured user questions with selectable options
- Subagents or isolated model sessions
- Browser automation and screenshots
- Image inspection
- Image or video generation
- Shell or script execution
- Local server management

Read [references/capabilities.md](references/capabilities.md) for preferred tools and fallbacks. Never pretend an unavailable capability was used.

Treat a browser harness as the preferred design surface whenever one is available. This may be agent-browser, a built-in browser tool, Playwright, Puppeteer, or another live browser controller. Prefer rendering, interaction, screenshots, and image inspection over inferring appearance from HTML and CSS.


## Choose the working mode

Infer the mode from the request and existing context. Ask only when the choice materially changes the work.

- **Direct build**: Implement the requested interface now.
- **Explore only**: Produce concepts or standalone artifacts without modifying the application.
- **Explore then build**: Produce concepts, get a selection, then implement the selected direction.
- **Review and refine**: Inspect an existing interface and improve it without replacing its product model.

When asking, prefer the harness's structured question tool. Provide 2 to 4 distinct options, explain the tradeoffs, and mark a recommendation. If no such tool exists, ask the same question in a normal message with numbered options and a clearly labeled recommendation.

Do not ask which mode to use when the user already made it clear. Direct requests such as "fix this component" or "build this page" default to direct build. Requests for options, concepts, mockups, or exploration use explore only or explore then build according to the requested endpoint.

## Preserve product truth

Before visual work:

1. Inspect the relevant application, routes, components, design system, content, and realistic states.
2. Identify behavior and information architecture that must not change.
3. Reuse the project's established components and extension points unless the design direction requires a deliberate, approved change.
4. For framework-owned surfaces such as admin panels, work through their supported theming and extension APIs rather than fighting generated markup.
5. Separate design problems from product or data-model problems. Surface scope changes instead of hiding them inside visual work.

Read [references/discovery.md](references/discovery.md) when requirements, constraints, or visual direction are not already explicit.

## Explore directions before converging

Use exploration when the user requests it, when the visual direction is genuinely open, or when a high-impact redesign would otherwise rely on arbitrary choices.

Generate 3 to 5 meaningfully different concepts. Vary the core idea, composition, density, typography, interaction model, and emotional effect. Color swaps and minor spacing changes are not separate concepts.

Use a mix of:

- Directions grounded in the product, audience, brand, or user's references
- One deliberately restrained direction
- One ambitious direction that tests the edge of what fits the product
- Seed-driven directions when outputs risk converging on familiar patterns

Generate exactly one seed inside each concept's isolated context:

```bash
python scripts/generate_seed.py --count 1 --format json
```

Do not generate a batch of seeds in the parent or share seeds between explorers. Each explorer should encounter only its own seed so sibling inspiration cannot blend in the same context. Treat the seed as private creative stimulus. Interpret it for subpatterns, rhythm, contrast, hierarchy, or metaphor. Do not display it in the interface or mechanically map characters to fixed design tokens. Record it with that concept so a useful direction can be reproduced.

Read [references/mockups.md](references/mockups.md) before producing multiple concepts or standalone artifacts.

## Parallel concept exploration

When subagents or isolated sessions are available, assign one concept to each explorer in parallel. Give every explorer the same product facts, constraints, output contract, and quality bar, but a different direction brief. After entering its isolated context, each explorer generates and uses its own seed. Do not pre-generate seeds in the parent, disclose sibling seeds, or let explorers see sibling concepts before their own work is complete.

Name one integration owner. Explorers should not edit the same application files. They should write to separate artifact directories or isolated worktrees.

Require each explorer to open its own concept in an available browser harness, exercise its representative interaction, capture screenshots at relevant widths, and inspect the screenshots before reporting completion. The integration owner must repeat browser inspection across the assembled gallery rather than trusting explorer claims.


When subagents are unavailable, create the concepts sequentially. Generate one new seed immediately before starting each concept, then keep that seed and its interpretation out of subsequent concept contexts as far as the harness allows. Reset the direction brief between concepts and avoid carrying visual decisions from one into the next. Preserve the same separation of outputs.

If only one concept is requested, do not create extra options for process theater.

## Present concepts for a decision

Make concepts runnable and comparable. Prefer realistic content and representative interaction over static decoration.

For standalone HTML concepts, create one self-contained entry file per concept when practical. Build a comparison gallery with:

```bash
python scripts/build_gallery.py \
  --title "Interface concepts" \
  --output <artifact-directory>/index.html \
  --item "Concept A=<artifact-directory>/concept-a.html" \
  --item "Concept B=<artifact-directory>/concept-b.html"
```

Open the gallery with the best available browser harness and verify every concept. Switch between concepts, exercise representative interactions, capture screenshots at relevant widths, and inspect the image output for composition, hierarchy, clipping, overflow, and unintended browser rendering. Reading HTML or capturing screenshots without viewing them is not visual verification. If browser automation is unavailable, provide the exact local file or server URL and simple opening instructions. Ask the user for screenshots only when the environment cannot capture them.

Present each option with:

- A short name and one-sentence thesis
- What makes it distinct
- Main product and implementation tradeoffs
- A browser link or artifact path
- A recommendation tied to the user's goals

Use a structured question tool with rich previews when available. Otherwise provide numbered options in a normal message. Do not implement a selected concept until the user has chosen when the request is explicitly exploratory.

## Build the selected direction

Write a compact direction brief before implementation. It must state:

- User and product goal
- Emotional target
- Visual thesis
- Composition and hierarchy
- Typography and color strategy
- Image and motion strategy
- Interaction character
- Constraints and preserved behavior
- Specific cliches or patterns to avoid
- The memorable element that earns the direction

Implement the smallest complete surface that proves the direction. Resolve composition and hierarchy before polishing micro-details. Use realistic content and cover meaningful states.

When a browser harness is available, preview the work in the live product route or artifact throughout implementation. After meaningful visual changes, capture and inspect screenshots instead of relying on source review. Exercise the real component states and responsive layouts before the critic pass.


For direct build mode, create the brief internally and proceed without pausing unless a material product decision requires the user.

## Use generated media deliberately

Consider custom imagery or motion when it carries the concept, communicates the product, or creates an effect that code cannot express economically. Do not add generated media merely to make a plain interface busier.

Preferred order:

1. Existing product assets
2. Purpose-built SVG, CSS, canvas, or WebGL
3. Available image-generation tools
4. Available video-generation tools for effects or state transitions that justify their weight
5. A clearly labeled placeholder plan only when the user requested concept work rather than a finished implementation

Before using a paid external generator, confirm cost-sensitive choices with the user unless they already authorized them. Read credentials from environment variables or ignored secret files. Never place secrets in prompts, source, logs, screenshots, artifacts, or critic packets.

If generation tools are unavailable, use existing or procedural assets, adapt the direction, or tell the user what asset is needed. Never claim generated media exists when it does not.

## Run an independent visual critic loop

After the first coherent implementation, review the rendered result rather than the source code.

Use screenshots as visual evidence only after an image-capable agent or tool has actually viewed them. File creation alone does not prove the rendered result is correct.


When an independent critic is available:

1. Run the real interface.
2. Capture representative screenshots.
3. Start a fresh critic context.
4. Provide only the screenshots, product purpose, direction brief, and optional quality references.
5. Exclude source code, implementation effort, previous critiques, and the implementer's rationale.
6. Request the structured output in [references/critic.md](references/critic.md).
7. Apply the highest-impact valid findings.
8. Capture fresh screenshots and repeat only while the result is materially improving.

Use the strongest suitable model for criticism and a capable, faster model for implementation when that split is available. A larger critic is optional, not a reason to block the work.

If no independent critic exists, perform a deliberate visual review from screenshots. Ignore implementation history, apply the same rubric, and label the result as self-review rather than independent review.

Default to two critic rounds. Continue to a third only when the findings are converging and another pass has clear value. Do not chase a numeric score indefinitely.

## Subtract before delivery

Run a dedicated subtraction pass. For every major element, ask whether it supports comprehension, action, hierarchy, product identity, or emotional effect. Remove decoration, labels, containers, copy, and custom controls that do not earn their place.

Watch for common agent-generated habits:

- Default hero composition with copy left and artwork right
- Purple or blue gradients used without product meaning
- Excessive cards, pills, glows, and rounded containers
- Generic abstract shapes instead of relevant imagery
- Repeated explanatory copy
- Motion without hierarchy or state meaning
- Custom controls that are weaker than native or project components
- Visual novelty that damages task completion

Restraint is not automatically minimalism. Preserve intentional density and expressive detail when they serve the direction.

## Verify and finish

Read [references/delivery.md](references/delivery.md) and verify the actual surface. A live browser session with inspected screenshots is the primary proof for visual work whenever the harness supports it.

Keep a verification ledger while working: exact viewport, concept or route, control exercised, observed result, and screenshot actually viewed. Cross-check the final report against that ledger. Never say "all concepts," "all tabs," or "all states" unless each one has explicit evidence; otherwise name only what was inspected.

Finish with:

- The implemented or exploratory outcome
- Paths or URLs for artifacts
- The selected direction and material tradeoffs
- What was verified in the real interface
- Any limitation caused by unavailable tools, assets, or user decisions

Do not claim visual verification if the interface was not rendered and inspected.