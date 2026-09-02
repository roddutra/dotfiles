# Mockup exploration

Use mockups to decide direction, not to delay implementation.

## When mockups add value

Create concepts when:

- The user asks to explore or compare directions
- The visual identity is open
- A high-impact redesign has several valid approaches
- A risky interaction needs validation before integration
- The application is expensive or disruptive to modify directly

Skip mockups when the request is narrow, the direction is already settled, or the user asked for immediate implementation.

## Concept contract

Each concept must:

- Solve the same user task with the same representative content
- Respect the same platform and product constraints
- Be runnable enough to evaluate its central interaction
- Differ in thesis, composition, hierarchy, and interaction character
- Use its own directory or isolated workspace
- Include a short direction brief and any seed used
- Be rendered, exercised, captured, and visually inspected by its explorer when a browser harness is available
- Include a framework-feasibility map when the final surface is constrained by Filament, an admin framework, or another component system; distinguish supported primitives from custom views

Do not let one explorer create every concept when independent sessions are available. Each explorer generates its own seed after entering its isolated context. The parent must not batch seeds or let explorers see sibling seeds, interpretations, or work until their concepts are complete.

The integration owner independently opens the assembled gallery, switches through every concept, exercises representative interactions, and inspects screenshots at relevant widths. Source review does not replace this pass.

## Artifact strategy

Prefer self-contained HTML, CSS, and JavaScript for concept work outside the application. Use the application's framework when fidelity to its components, routing, data, or responsive behavior is essential.

Keep temporary concepts outside production source when possible. Use a project-approved ignored directory, an isolated worktree, or a system temporary directory. Do not leave experimental routes, dependencies, assets, or components in the final application.

Use realistic content. Placeholder rectangles and lorem ipsum hide hierarchy and overflow problems.

## Comparison gallery

The bundled gallery script creates a local shell that switches between concept entry files and offers desktop, tablet, and mobile viewport widths. It does not modify concepts.

```bash
python scripts/build_gallery.py \
  --title "Dashboard directions" \
  --output <artifact-directory>/index.html \
  --item "Editorial=<artifact-directory>/editorial.html" \
  --item "Instrument panel=<artifact-directory>/instrument.html" \
  --item "Quiet utility=<artifact-directory>/utility.html"
```

Open the gallery through a local server when concepts use modules, fetch requests, or browser features blocked by `file://`. Otherwise the file URL is sufficient. In either case, prefer an available browser harness, capture screenshots, and view the images rather than merely confirming that files exist.

## Selection

Present 3 to 5 concepts with:

- Name
- Thesis
- Memorable element
- Main strength
- Main risk
- Artifact URL or path
- Recommendation

Ask the user to select one, combine named aspects, or reject all. Prefer a structured question tool with previews. If it is unavailable, use numbered choices in a normal message.

Do not merge every liked detail into one direction. Preserve a coherent thesis.
