# Other Diagram Types Reference

## Table of Contents

1. [State Diagram](#state-diagram)
2. [User Journey](#user-journey)
3. [Gantt Chart](#gantt-chart)
4. [Mindmap](#mindmap)
5. [Pie Chart](#pie-chart)
6. [ER Diagram](#er-diagram)
7. [Class Diagram](#class-diagram)
8. [GitGraph](#gitgraph)
9. [Timeline](#timeline)
10. [Kanban](#kanban)
11. [Architecture](#architecture)
12. [Block Diagram](#block-diagram)

---

## State Diagram

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Processing: Submit
    Processing --> Done: Complete
    Processing --> Error: Fail
    Error --> Idle: Retry
    Done --> [*]

    state Processing {
        [*] --> Validating
        Validating --> Executing
        Executing --> [*]
    }
```

Key syntax:

- `[*]` = start/end pseudo-state
- `state Name { }` = composite/nested states
- `<<fork>>` and `<<join>>` for parallel states
- `<<choice>>` for choice pseudo-state
- Notes: `note right of State: Text`
- Direction: `direction LR` inside state blocks

---

## User Journey

```mermaid
journey
    title My Working Day
    section Morning
        Wake up: 3: Me
        Commute: 1: Me, Bus Driver
        Start work: 4: Me
    section Afternoon
        Lunch: 5: Me, Colleague
        Code review: 3: Me, Colleague
    section Evening
        Go home: 2: Me
```

Key syntax:

- `title` sets the diagram title
- `section Name` groups tasks
- Task format: `Task name: score: actor1, actor2`
- Score: 1 (negative) to 5 (positive)

---

## Gantt Chart

```mermaid
gantt
    title Project Plan
    dateFormat YYYY-MM-DD
    excludes weekends

    section Phase 1
        Research       :done, a1, 2025-01-06, 10d
        Design         :active, a2, after a1, 15d

    section Phase 2
        Development    :crit, a3, after a2, 20d
        Testing        :a4, after a3, 10d

    section Milestones
        Launch         :milestone, m1, after a4, 0d
```

Key syntax:

- `dateFormat` sets input format (default `YYYY-MM-DD`)
- `axisFormat` sets display format (e.g. `%Y-%m-%d`)
- Tags: `done`, `active`, `crit`, `milestone` (applied before dates)
- Duration: `10d`, `1w`, or specific end date
- Dependencies: `after taskId`
- `excludes weekends` or specific dates
- `todayMarker off` to hide today marker
- `tickInterval 1week` to set axis ticks
- `until` keyword (v10.9.0+): task runs until another task starts

---

## Mindmap

```mermaid
mindmap
    root((Central Topic))
        Branch A
            Leaf A1
            Leaf A2
        Branch B
            Leaf B1
                Sub-leaf
        Branch C
```

Key syntax:

- Indentation defines hierarchy (any consistent indentation works)
- Node shapes follow flowchart conventions: `(Rounded)`, `[Square]`, `((Circle))`, `))Bang((`, `{Cloud}`
- Icons: `::icon(fa fa-book)` after node text
- Classes: `:::className` after node text
- Layout option: `layout: tidy-tree` in frontmatter config

---

## Pie Chart

```mermaid
pie title Browser Share
    "Chrome" : 65
    "Firefox" : 15
    "Safari" : 12
    "Other" : 8
```

Key syntax:

- `pie showData` to display values on the chart
- Values can be raw numbers or percentages (Mermaid calculates proportions)
- `title` is optional

---

## ER Diagram

```mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ LINE_ITEM : contains
    PRODUCT ||--o{ LINE_ITEM : "is in"
    CUSTOMER {
        int id PK
        string name
        string email UK
    }
    ORDER {
        int id PK
        date created
        int customer_id FK
    }
```

Relationship syntax:

- `||` = exactly one
- `o|` = zero or one
- `}|` = one or more
- `}o` = zero or more
- Left side `--` right side, e.g. `||--o{` = one-to-zero-or-many
- Attribute types: `type name` with optional `PK`, `FK`, `UK` constraints

---

## Class Diagram

```mermaid
classDiagram
    class Animal {
        +String name
        +int age
        +makeSound() void
    }
    class Dog {
        +fetch() void
    }
    Animal <|-- Dog : inherits

    class Cat {
        +purr() void
    }
    Animal <|-- Cat
```

Relationships:

- `<|--` inheritance
- `*--` composition
- `o--` aggregation
- `-->` association
- `..>` dependency
- `..|>` realisation

Visibility: `+` public, `-` private, `#` protected, `~` package.

---

## GitGraph

```mermaid
gitGraph
    commit
    commit
    branch develop
    checkout develop
    commit
    commit
    checkout main
    merge develop
    commit
    branch feature
    commit
    checkout main
    merge feature
```

Key syntax:

- `commit id: "msg"` or `commit tag: "v1.0"`
- `commit type: HIGHLIGHT` or `REVERSE` or `NORMAL`
- `branch name`, `checkout name`, `merge name`
- `cherry-pick id: "commitId"`
- Frontmatter config: `gitGraph TB` for top-bottom orientation

---

## Timeline

```mermaid
timeline
    title Project History
    2023 : Founded company
         : Hired first team
    2024 : Launched MVP
         : Series A funding
    2025 : Scaled to 50 employees
```

Key syntax:

- Time periods on their own line, followed by events prefixed with `:`
- Multiple events per time period on subsequent indented lines
- `section Name` to group time periods

---

## Kanban

```mermaid
kanban
    column1[To Do]
        task1[Design homepage]
        task2[Write copy]
    column2[In Progress]
        task3[Build API]
    column3[Done]
        task4[Set up CI/CD]
```

Key syntax:

- Columns defined with `columnId[Title]`
- Tasks nested under columns with `taskId[Title]`
- Metadata via `@{ priority: "high", assigned: "Rod" }` after task
- `ticketBaseUrl` in config for auto-linking ticket IDs

---

## Architecture

```mermaid
architecture-beta
    group cloud(cloud)[Cloud Platform]

    service api(server)[API Server] in cloud
    service db(database)[PostgreSQL] in cloud
    service cache(database)[Redis] in cloud
    service client(internet)[Web Client]

    client:R --> L:api
    api:R --> L:db
    api:B --> T:cache
```

Key syntax:

- `group name(icon)[Label]` — groups with optional icon
- `service name(icon)[Label] in groupName` — services
- Connections: `service1:edge --> edge:service2`
- Edge positions: `T` (top), `B` (bottom), `L` (left), `R` (right)
- Icons: Built-in set includes `cloud`, `server`, `database`, `disk`, `internet`, `github`

---

## Block Diagram

```mermaid
block-beta
    columns 3
    A["Frontend"] B["API Gateway"] C["Backend"]
    space D["Database"] space

    A --> B --> C
    C --> D
```

Key syntax:

- `columns N` sets grid width
- `space` creates empty cells
- Blocks span columns: `A["Wide"]:2` spans 2 columns
- Nested blocks: `block:groupName ... end`
- Shapes use flowchart conventions: `()`, `{}`, `[]`, `(())`, etc.

---

## Common Configuration (All Diagrams)

Frontmatter config block (placed before diagram declaration):

```mermaid
---
config:
  theme: dark
  look: handDrawn
  flowchart:
    curve: basis
    defaultRenderer: elk
---
flowchart TD
    A --> B
```

Available themes: `default`, `dark`, `forest`, `neutral`, `base`.

Look options (v11+): `classic`, `handDrawn`.

Layout engines: `dagre` (default), `elk` (better for complex diagrams).
