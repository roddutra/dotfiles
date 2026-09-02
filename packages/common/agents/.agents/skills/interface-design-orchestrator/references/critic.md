# Independent visual critic

Judge the rendered interface against its intended direction and product purpose. Ignore implementation cost.

## Critic packet

Provide:

- Product purpose and primary user task
- Direction brief
- Screenshots at representative viewports and states
- Optional professional references or moodboard labeled as calibration, not copying targets

Exclude:

- Source code
- Previous critique
- Implementation history
- Time spent
- Implementer's rationale
- Desired score or stopping threshold

Use the same critic prompt across iterations so scores remain comparable.

## Critic prompt

```text
Evaluate this rendered interface as an independent design critic.

First infer what visual direction it is attempting. Compare the execution with how an excellent product design studio would realize that direction while preserving the stated user task.

Inspect both overall composition and fine detail. Penalize familiar agent-generated patterns, unjustified decoration, weak hierarchy, inaccessible choices, and novelty that harms usability. Treat references as a quality baseline, not designs to copy.

Return the requested structured review. Be specific, concise, bold, and evidence-based.
```

## Output contract

```text
Score: <0-10>
Direction read: <one sentence>

Strengths:
- <specific strength>

Highest-impact gaps:
1. Problem: <visible problem>
   Evidence: <where it appears>
   Why it matters: <effect on product or direction>
   Change: <specific recommendation>

Agent-generated cliches:
- <pattern or "None observed">

Usability or accessibility risks:
- <risk or "None observed">

Next iteration focus:
- <single highest-value focus>
```

Limit highest-impact gaps to three. A critic that returns a long wish list has not prioritized.

## Evaluation dimensions

- Product fit and task clarity
- Conceptual coherence
- Composition and hierarchy
- Typography
- Color and contrast
- Imagery and iconography
- Interaction and motion
- Responsive behavior
- Accessibility
- Restraint and removal of unearned elements
- Distinctiveness without novelty for its own sake
- Detail quality

## Iteration policy

- Default to two critic rounds.
- Apply only findings supported by the rendered interface and product constraints.
- Rebuild composition before polishing details when structure is the main problem.
- Continue to a third round only when the review is converging and the next change is clear.
- Stop when remaining findings are low-impact, contradictory, or outside scope.
- Do not alter the critic prompt to obtain a higher score.
- Do not treat a score as proof. The visible result and product behavior remain authoritative.
