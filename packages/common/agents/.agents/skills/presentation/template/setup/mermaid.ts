// Reads the brand tokens from styles/index.css so diagrams match the slides.
// Slidev renders Mermaid inside a shadow root, so styles/index.css cannot
// reach the diagram: shape styling goes in themeCSS below.
export default async () => {
  const css = getComputedStyle(document.documentElement)
  const token = (name: string) => css.getPropertyValue(`--brand-${name}`).trim()
  const font = token('font-body')

  // Mermaid sizes each node from the label's measured width. Measuring before
  // the web font arrives sizes boxes for the fallback font and clips labels.
  await Promise.all([
    document.fonts.load(`400 16px ${font}`),
    document.fonts.load(`500 16px ${font}`),
  ]).catch(() => {})

  return {
    theme: 'base',
    themeVariables: {
      fontFamily: font,
      background: token('bg'),
      primaryColor: token('surface'),
      primaryTextColor: token('text'),
      primaryBorderColor: token('primary'),
      secondaryColor: token('bg'),
      tertiaryColor: token('surface'),
      lineColor: token('muted'),
      textColor: token('text'),
      noteBkgColor: token('surface'),
      noteBorderColor: token('accent'),
      dropShadow: 'none',
      useGradient: false,
    },
    // Mermaid wraps labels at 120px by default. Break lines with <br/> instead.
    // Leave fontSize alone: Mermaid measures labels at 16px whatever it is set
    // to. Enlarge a diagram with the fence's {scale: n} option.
    flowchart: { padding: 18, rankSpacing: 36, wrappingWidth: 400 },
    // Mermaid sizes nodes from SVG text metrics (about 1.25em a line) but draws
    // HTML labels at line-height 1.5, so multi-line labels outgrow their boxes.
    // Match the line height and let any rounding spill rather than clip.
    themeCSS: `
      .nodeLabel, .edgeLabel { font-family: ${font}; letter-spacing: normal; }
      foreignObject { overflow: visible; }
      foreignObject > div { line-height: 1.25 !important; }
      .node rect { rx: ${token('radius')}; ry: ${token('radius')}; }
      .node :is(rect, path, polygon, circle) { filter: none; stroke-width: 1.5px; }
    `,
  }
}
