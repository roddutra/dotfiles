# Delivery and verification

Verify the real rendered surface after implementation and after cleanup.

## Functional preservation

- Primary user task works end to end
- Navigation and links reach the correct destinations
- Forms preserve validation, errors, disabled states, and submission behavior
- Loading, empty, error, permission, and long-content states remain usable
- Existing product behavior changed only where approved
- Framework-owned surfaces use supported extension points

## Visual inspection

Inspect at minimum:

- Desktop viewport
- Mobile viewport
- One intermediate width
- Primary interaction states
- Representative real content
- Long titles, labels, values, and lists
- Empty and error states when the surface supports them

Check:

- Hierarchy is legible at a glance
- Typography wraps intentionally
- Alignment and spacing are optically sound
- Interactive targets are large enough
- Contrast and focus states are visible
- Motion communicates hierarchy or state
- Reduced-motion behavior is safe
- Generated or custom media loads correctly
- No clipped, overlapping, or overflowing content
- No accidental horizontal scrolling
- No obvious agent-generated cliches remain without purpose

## Runtime proof

Prefer browser automation to:

1. Open the actual route or artifact.
2. Exercise the changed interaction.
3. Capture screenshots at representative widths and states.
4. View the screenshots with an image-capable tool or agent and assess visible composition, hierarchy, rendering, clipping, and overflow.
5. Inspect console and failed network requests when the tool exposes them.
6. Compare against the original rendered surface for refactors.

Record each check as it happens: route or concept, viewport, interaction, observed state, screenshot path, and whether the image was viewed. Use this evidence ledger to write the delivery report. A collective claim such as "all tabs verified" requires one recorded check per tab.

If browser automation is unavailable:

1. Start the correct local server when possible.
2. Provide the exact URL or file path.
3. Ask the user to inspect or send screenshots only when no capture path exists.
4. State that visual verification remains incomplete.

Do not substitute source inspection, a passing unit test, or uninspected screenshot files for rendered proof.

## Cleanup

After the direction is proven:

- Remove rejected concepts from production code
- Remove temporary routes, dependencies, assets, and debug controls
- Keep standalone artifacts only when the user requested them as deliverables
- Preserve the selected direction brief if the project has an established design-decision location
- Run the smallest applicable formatter, checks, and changed-contract tests
- Reopen the final surface after cleanup

## Delivery report

Report:

- What was built or explored
- Selected direction and material tradeoffs
- Application files or artifact paths
- Viewports and interactions inspected
- Critic rounds completed and highest-impact changes
- Any verification limitation or unresolved user decision
