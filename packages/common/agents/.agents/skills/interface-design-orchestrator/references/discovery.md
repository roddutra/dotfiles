# Discovery and direction brief

Resolve product truth before visual invention.

## Inspect first

For an existing application, inspect only the relevant surface and its established patterns:

- Route and entry component
- Parent layout and navigation
- Shared design-system components and tokens
- Real data shape and representative content
- Loading, empty, error, disabled, and permission states
- Responsive behavior
- Existing tests or stories that define behavior
- Framework extension points and constraints

Do not introduce a second component convention beside an existing one without a deliberate cutover.

## Ask only material questions

Ask when different answers would lead to meaningfully different interfaces and the repository cannot answer them. Useful topics include:

- Primary user and task
- Desired emotional effect
- Brand boundaries
- Density and information priority
- Whether the user wants exploration or immediate implementation
- Whether generated media and external cost are acceptable
- Which behavior or content may change

Offer concrete options and a recommendation. Avoid asking the user to restate facts available in the product or code.

## Direction brief

Keep the brief compact and decision-oriented:

```text
Product goal:
Primary user and task:
Emotional target:
Visual thesis:
Composition and hierarchy:
Typography and color:
Imagery and motion:
Interaction character:
Preserved behavior:
Constraints:
Avoid:
Memorable element:
Seed, if used:
```

A useful thesis names a specific relationship between product and form. "Modern and clean" is not a direction.

## Existing interface work

For refactors and improvements:

1. Reproduce the current surface in the browser.
2. Identify the user-visible problem before editing.
3. Preserve behavior unless the user approves a product change.
4. Decide whether the problem needs local refinement, structural redesign, or exploratory concepts.
5. Compare the final surface against the same content and viewport used at the start.

## New interface work

For a new page, view, or component:

1. Find the closest established product pattern.
2. Reuse its data, navigation, state, and accessibility conventions.
3. Define what must be distinctive and what should remain familiar.
4. Build realistic states rather than a happy-path shell.
