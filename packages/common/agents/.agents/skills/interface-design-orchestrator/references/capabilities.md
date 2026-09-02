# Capability fallbacks

Use the best available mechanism. Preserve the workflow when a preferred tool is absent.

When any live browser controller is available, prefer it for interface work. Detect the installed harness rather than requiring a product name. agent-browser is one valid example, not a dependency.

| Need | Preferred capability | Fallback |
| --- | --- | --- |
| Material user decision | Structured question tool with 2 to 4 options, tradeoffs, and a recommendation | Normal message with numbered options and a labeled recommendation |
| Independent concepts | Parallel subagents or isolated sessions | Sequential concepts with separate briefs and output directories |
| Independent criticism | Fresh model session that receives screenshots only | Screenshot-led self-review that explicitly ignores implementation history |
| Rendered inspection | Available live browser harness with interaction, screenshots, and image inspection | Start a local server and provide the URL; ask the user for screenshots only if capture is impossible |
| Image inspection | Native vision or image-read tool | Ask the user to describe the problem or provide a screenshot to a capable environment |
| Image generation | Native image tool or approved external provider | Existing assets, licensed stock supplied by the user, SVG, CSS, canvas, or a revised direction |
| Video generation | Native video tool or approved external provider | CSS, SVG, canvas, WebGL, or conventional transition implementation |
| Script execution | Shell or process tool | Reproduce the small deterministic operation with available file tools |
| Long-running server | Managed process or service tool | Foreground command with clear stop instructions, or static file URLs |

## Rules

- Inspect available tools instead of assuming names or brands.
- Prefer structured questions only for choices the user should weigh. Do not interrupt obvious work.
- Include previews in a structured question when the harness supports them.
- Require concept explorers and the integration owner to inspect their own rendered output.
- Capture screenshots at representative widths and view the image content. A saved screenshot that nobody inspected is not verification.
- If a tool requires a plugin or extension, use it only when already available. Do not make installation a hidden prerequisite.
- When a fallback weakens independence or verification, state the limitation precisely.
- Never substitute an unavailable capability with a fabricated result.
