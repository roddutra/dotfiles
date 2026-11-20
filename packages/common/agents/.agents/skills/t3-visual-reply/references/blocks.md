# Payload and blocks

```json
{
  "schema_version": 1,
  "title": "Lefthook in worktrees",
  "blocks": [
    { "type": "lede", "text": "Commit checks skip in new worktrees." },
    {
      "type": "decision",
      "question": "Install Lefthook with Homebrew?",
      "recommended": "brew",
      "options": [
        { "id": "brew", "label": "Install with Homebrew", "pros": ["Checks run everywhere"], "cons": ["One more global tool"] },
        { "id": "leave", "label": "Leave it", "cons": ["Checks keep skipping"] }
      ]
    }
  ]
}
```

Top-level fields, all required:

- `schema_version`: `1`
- `title`: page title for `html_render`, up to 200 characters
- `blocks`: at least one block

Unknown fields fail validation. Optional fields are marked "optional".

## Inline formatting

Every text field is escaped, then supports `` `code` ``, `**bold**` and `[label](https://url)`. Only `http` and `https` links are allowed; they open in the browser.

## Blocks

### `lede`

The opening statement.

- `text`
- `sub`: optional supporting sentence

### `heading`

- `text`

### `text`

- `text`
- `muted`: optional boolean

### `list`

- `items`: strings
- `ordered`: optional boolean

### `callout`

- `tone`: optional, `info` (default), `success`, `warning`, `danger` or `neutral`
- `title`: optional
- `text`: required unless `items` is given
- `items`: optional strings

### `facts`

Key numbers or values shown as small tiles.

- `items`: `{ "label", "value" }`

### `cards`

Up to three per row on desktop, stacked on phones.

- `items`: objects with:
  - `title`
  - `tag`: optional pill label
  - `tone`: optional, colours the tag and highlight
  - `text`: optional
  - `items`: optional bullet strings
  - `highlight`: optional boolean, outlines the card in its tone

### `steps`

A numbered sequence or flow.

- `items`: `{ "title", "text" }`, `text` optional

### `table`

The first cell of each row is styled as a row header.

- `columns`: strings
- `rows`: arrays of strings, each the same length as `columns`
- `caption`: optional

### `code`

Shown verbatim, no inline formatting.

- `code`
- `caption`: optional

### `decision`

Two options sit side by side; three or four become full-width rows. Everything stacks on phones.

- `question`
- `context`: optional
- `required`: optional, default `true` ("Needs your choice"); `false` shows "Optional, your call"
- `recommended`: optional option `id`
- `options`: 2-4 objects with:
  - `id`: reply token, lowercase `a-z`, `0-9`, space, `+` or `-`, up to 24 characters, unique
  - `label`
  - `summary`: optional
  - `pros`: optional strings
  - `cons`: optional strings

### `status`

The count is `done` divided by all items. Completed items collapse behind a disclosure.

- `title`
- `source`: where the data came from, for example ``"`docs/prd/014.md` checklist"``
- `as_of`: local timestamp of the read
- `done`: optional strings
- `working`: optional strings
- `next`: optional strings
- `waiting`: optional, strings or `{ "text", "on" }` where `on` names the blocker

At least one list must be non-empty.

### `details`

A collapsed disclosure. Nesting is limited to three levels.

- `summary`
- `blocks`: nested blocks
- `open`: optional boolean

### `html`

The escape hatch, inserted unescaped. See the rules in `SKILL.md`.

- `html`: a fragment, not a full document
- `css`: optional
