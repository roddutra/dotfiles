---
name: personal-writer
description: Write authentic, human-feeling content in the user's personal voice for emails, blog posts, messages, and personal communications. Use when writing content the user will share as their own, or when the user asks to write in their voice, style, or as them.
---

# Personal Writer

Write content that feels authentic and human, not AI-generated. This applies when writing emails, blog posts, messages, or any text the user will share as their own work.

## Core Requirements

### Language and Tone

- **Australian English**: Use Australian/British spellings and conventions (organise, colour, favour)
- **Default tone**: Friendly and informal, like writing to a friend
- **Adapt as needed**: Adjust formality based on context (formal for cover letters, casual for friends, business-casual for clients)

### Output Format

**Defaults** (override if user specifies otherwise):
- **Long-form** (blog posts, articles): Markdown artifact (.md file)
- **Short-form** (emails, messages): Directly in chat response
- **Other formats** (.docx, .pdf): Only when explicitly requested

## Avoid AI Patterns

Cut these entirely:

1. **Gerunds as subjects**: "Implementing new processes" → "New processes"
2. **"Not only/but also"**: Use only for genuine emphasis, otherwise simplify
3. **Summary phrases**: Delete "in conclusion," "overall," "in summary," "for the reasons stated above"
4. **Empty transitions**: Cut "in this day and age," "it's important to note that," "additionally, by," "with that being said"
5. **Wordy prepositions**: "in a systematic manner" → "systematically," "in the near future" → "soon"
6. **Nominalizations**: "perform an analysis" → "analyse," "make a decision" → "decide"
7. **Bland AI vocabulary**: 
   - Avoid: delve, realm, multitude, leverage, utilise, facilitate, implement, optimise, enhance, robust, streamline, innovative, cutting-edge, ecosystem, landscape, space
   - Use: Concrete, specific alternatives
8. **Bloat and redundancy**: "however, despite" → "despite," "assist in helping" → "help," "exact replica" → "replica"

### Additional Rules

- **No em/en dashes**: Use commas, parentheses, or full stops instead
- **No helpers/hedgers**: Cut "I just wanted to," "I think that," "kind of," "sort of," "basically," "actually" unless necessary
- **No AI openers**: Avoid "In today's...," "It's important to note...," "Let me explain..."
- **No AI closers**: Replace "Please don't hesitate..." with "Let me know...," keep "Thanks" simple

## Writing Guidelines

- **Be concrete**: Replace vague terms ("soon" → "next week," "some people" → "three colleagues")
- **Use active voice**: Prefer "The team wrote the report" over "The report was written by the team"
- **Show, don't tell**: Demonstrate claims rather than stating them ("handles 10,000 requests/sec" vs "robust system")
- **Natural contractions**: Use contractions in informal writing (I'm, you're, can't)
- **Vary sentence length**: Mix short and medium sentences, avoid nested complexity

## When NOT to Apply

- User is asking for information or analysis
- Creating professional documents in a specific institutional voice
- User specifically requests a different style
- Writing technical documentation requiring formal precision
