/* Panel report kit: helpers that turn study data into kit markup.
   Their inputs are small shapes derived from the study files (kit.html, "Helpers", shows how), not the files as they are.
   Every helper writes plain HTML that kit.css styles, so a page may also write that HTML by hand. */
(function () {
  const PP = (window.PP = {});
  const h = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  };
  const sr = (text) => h("span", "pp-sr", text);
  const plural = (n, w) => n + " " + w + (n === 1 ? "" : "s");
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const flat = (label) => (Array.isArray(label) ? label.join(" ") : label); /* a two-line chart label, as one line of text */
  const root = document.documentElement;

  /* Tooltips: any element with data-tip. Works with mouse and keyboard focus. */
  let tip;
  const show = (t) => {
    if (!tip) { tip = h("div", "pp-tip"); tip.setAttribute("role", "tooltip"); document.body.appendChild(tip); }
    tip.textContent = t.dataset.tip;
    const r = t.getBoundingClientRect();
    tip.hidden = false;
    const half = tip.offsetWidth / 2;
    tip.style.left = Math.max(half + 8, Math.min(window.innerWidth - half - 8, r.left + r.width / 2)) + "px";
    tip.style.top = Math.max(tip.offsetHeight + 14, r.top) + "px";
  };
  const hide = () => { if (tip) tip.hidden = true; };
  document.addEventListener("mouseover", (e) => { const t = e.target.closest("[data-tip]"); t ? show(t) : hide(); });
  document.addEventListener("focusin", (e) => { const t = e.target.closest("[data-tip]"); t ? show(t) : hide(); });
  document.addEventListener("scroll", hide, true);

  /* ---------- Colour roles ----------
     A tone is a meaning. Series tones (s1 to s6, and "for" and "against" on an interview page) mark identity.
     Status tones (good, warn, crit, serious) mark a state. Neutral tones (n1 to n4, quiet, ink) carry no meaning. */
  const css = (name) => getComputedStyle(root).getPropertyValue(name).trim();
  const SERIES = ["s1", "s2", "s3", "s4", "s5", "s6"];
  const NEUTRAL = ["n1", "n2", "n3", "n4"];
  const TONES = { for: "--pp-s1", against: "--pp-s3", good: "--pp-good", warn: "--pp-warn", crit: "--pp-crit", serious: "--pp-serious", quiet: "--pp-n3", ink: "--pp-ink-2", accent: "--pp-accent" };
  SERIES.concat(NEUTRAL).forEach((t) => (TONES[t] = "--pp-" + t));
  const toneVar = (tone) => (TONES[tone] ? "var(" + TONES[tone] + ")" : null);

  /* One square per simulated participant, in a fixed run order, so a column of them lines up down a table.
     groupOf(run) returns a class (r, n, b, on, or "" for none); labels name each class for the tooltip and screen readers.
     The default labels are the interview groups. */
  const GROUPS = { r: "raised it", n: "said it is not a problem", b: "both", x: "no note under this theme" };
  PP.units = function (runs, groupOf, labels) {
    const names = Object.assign({}, GROUPS, labels || {});
    const box = h("span", "pp-units");
    runs.forEach((run) => {
      const g = groupOf(run) || "x";
      const u = h("span", "pp-u " + (g === "x" ? "" : g));
      u.dataset.tip = run + ": " + (names[g] || g);
      u.tabIndex = 0;
      u.appendChild(sr(u.dataset.tip + ". "));
      box.appendChild(u);
    });
    return box;
  };

  /* Themes table. themes: quant.json "themes", each optionally with kinds: {problem, background}, the theme's
     notes other than "not a problem" notes, counted by what they describe (a problem or workaround, or background).
     runs: quant.json runs.interviewed. opts: {definitions, group: (theme) => heading, labels}. */
  PP.themes = function (target, themes, runs, opts) {
    opts = opts || {};
    const kinds = themes.some((t) => t.kinds);
    const table = h("table", "pp-table");
    const head = table.createTHead().insertRow();
    const cols = ["Theme", "Participants", "Raised it", "Not a problem", "Both"].concat(kinds ? ["What their notes were"] : []).concat(["Evidence, among Raised and Both"]);
    cols.forEach((t, i) => { const th = h("th", i >= 2 && i <= 4 ? "n" : i >= 5 ? "wrap" : "", t); th.scope = "col"; head.appendChild(th); });
    const body = table.createTBody();
    let group = null;
    themes.forEach((t) => {
      if (opts.group) {
        const g = opts.group(t);
        if (g !== group) { group = g; const gr = body.insertRow(), th = h("th", "", g); th.colSpan = cols.length; th.scope = "colgroup"; gr.className = "group"; gr.appendChild(th); }
      }
      const row = body.insertRow();
      const name = h("th", "", t.name);
      name.scope = "row";
      if (opts.definitions !== false && t.definition) name.appendChild(h("span", "sub", t.definition));
      row.appendChild(name);
      const inSet = (k) => new Set(t[k].runs);
      const r = inSet("raised"), n = inSet("not_a_problem"), b = inSet("both");
      row.insertCell().appendChild(PP.units(runs, (run) => (r.has(run) ? "r" : n.has(run) ? "n" : b.has(run) ? "b" : "x"), opts.labels));
      [t.raised.n, t.not_a_problem.n, t.both.n].forEach((v) => row.appendChild(h("td", "n", v)));
      const list = () => h("div", "pp-evid");
      const bit = (box, count, label) => {
        const s = h("span", count ? "" : "zero");
        s.appendChild(h("b", "", count));
        s.appendChild(document.createTextNode(" " + label));
        box.appendChild(s);
      };
      if (kinds) {
        const k = t.kinds || { problem: 0, background: 0 }, box = list();
        bit(box, k.problem, "a problem or workaround");
        bit(box, k.background, "background");
        row.insertCell().appendChild(box);
      }
      const ev = list();
      bit(ev, t.unprompted.n, "unprompted");
      bit(ev, t.incident.n, "with an incident");
      const EFFORT = { workaround: "with a workaround", search: "searched for a fix", paid: "paid for something" };
      Object.keys(t.effort || {}).forEach((k) => { if (k !== "none" && k !== "unknown") bit(ev, t.effort[k].n, EFFORT[k] || k); });
      const f = t.flagged || { n: 0, of: 0 };
      bit(ev, f.n, "of " + f.of + " notes on a flagged question");
      row.insertCell().appendChild(ev);
    });
    target.replaceChildren(table);
    return table;
  };

  /* Model agreement. rows: quant.json "model_agreement"; models: the model keys; names maps a theme id to its name. */
  PP.agreement = function (target, rows, models, names, personaNames) {
    const table = h("table", "pp-table");
    const head = table.createTHead().insertRow();
    ["Persona", "Theme"].concat(models).concat(["Told of on"]).forEach((t, i) => {
      const th = h("th", i >= 2 && i < 2 + models.length ? "c" : "", t);
      th.scope = "col";
      head.appendChild(th);
    });
    const body = table.createTBody();
    rows.forEach((a) => {
      const row = body.insertRow();
      if (!a.agree) row.className = "solo";
      row.insertCell().textContent = (personaNames && personaNames[a.persona]) || a.persona;
      row.insertCell().textContent = names[a.theme] || a.theme;
      let told = 0;
      models.forEach((m) => {
        const yes = a.models[m] && a.models[m].n > 0;
        told += yes ? 1 : 0;
        const td = h("td", "c");
        td.appendChild(h("span", "pp-mark " + (yes ? "yes" : "no")));
        td.appendChild(sr(yes ? "told of" : "not told of"));
        row.appendChild(td);
      });
      row.insertCell().textContent = told === models.length ? "every model" : told + " of " + models.length + " models";
    });
    target.replaceChildren(table);
    return table;
  };

  /* Bar list. rows: [{label, n}]. One measure, the value always printed. Neutral grey unless opts.tone names
     a state (good, warn, crit) or a series (for, s1 ...). opts: {max, unit, tone, wrap}. */
  PP.bars = function (target, rows, opts) {
    opts = opts || {};
    const max = opts.max || Math.max.apply(null, rows.map((r) => r.n).concat([1]));
    const state = ["good", "warn", "crit"].includes(opts.tone);
    const dl = h("dl", "pp-bars" + (state ? " " + opts.tone : "") + (opts.wrap ? " wrap" : ""));
    dl.style.setProperty("--max", max);
    if (!state && toneVar(opts.tone)) dl.style.setProperty("--pp-c", toneVar(opts.tone));
    rows.forEach((r) => {
      dl.appendChild(h("dt", "", r.label));
      const dd = h("dd");
      const bar = h("div", "bar");
      bar.style.setProperty("--n", r.n);
      bar.dataset.tip = r.label + ": " + r.n + (opts.unit ? " " + opts.unit : "");
      dd.appendChild(bar);
      dl.appendChild(dd);
      dl.appendChild(h("dd", "val", r.n));
    });
    target.replaceChildren(dl);
    return dl;
  };

  /* The numbers behind a chart, in a light fold under it. */
  const numbers = (headers, rows) => {
    const d = h("details", "pp-fold plain");
    d.appendChild(h("summary", "", "The numbers"));
    const body = h("div", "body"), scroll = h("div", "pp-scroll"), table = h("table", "pp-table");
    const hr = table.createTHead().insertRow();
    headers.forEach((t, i) => { const th = h("th", i ? "n" : "", t); th.scope = "col"; hr.appendChild(th); });
    const tb = table.createTBody();
    rows.forEach((r) => { const tr = tb.insertRow(); r.forEach((v, i) => { const c = h(i ? "td" : "th", i ? "n" : "", flat(v)); if (!i) c.scope = "row"; tr.appendChild(c); }); });
    scroll.appendChild(table); body.appendChild(scroll); d.appendChild(body);
    return d;
  };
  const figure = (o) => {
    const fig = h("figure", "pp-chart");
    if (o.title) { const c = h("figcaption", "", o.title); if (o.note) c.appendChild(h("small", "", o.note)); fig.appendChild(c); }
    return fig;
  };

  /* Dot plot for scores on one scale. rows: [{label, sub, mean, values: [v or {v, who}], tone}].
     opts: {min, max, ticks, title, note, tone, dense, numbers: "summary" (default), "all" (every value) or false, digits}.
     A row's tone (or opts.tone) colours its mean, for a page whose series mean something; else the mean is ink. */
  PP.dotplot = function (target, rows, opts) {
    const digits = opts.digits === undefined ? 1 : opts.digits;
    const fmt = (v) => (typeof v === "number" ? v.toFixed(digits) : v);
    const val = (v) => (v && v.v !== undefined ? v.v : v);
    const x = (v) => ((v - opts.min) / (opts.max - opts.min)) * 100 + "%";
    const fig = figure(opts);
    const plot = h("div", "pp-dotplot" + (opts.dense ? " dense" : ""));
    const ticks = opts.ticks || [opts.min, opts.max];
    if (ticks.length > 1) plot.style.setProperty("--grid", 100 / (ticks.length - 1) + "%"); /* gridlines sit on evenly spaced ticks */
    const said = [];
    rows.forEach((r) => {
      const label = h("div", "label", r.label);
      if (r.sub) label.appendChild(h("span", "sub", r.sub));
      plot.appendChild(label);
      const track = h("div", "track");
      const tone = toneVar(r.tone || opts.tone);
      if (tone) track.style.setProperty("--pp-c", tone);
      const vs = (r.values || []).map(val);
      (r.values || []).forEach((v) => {
        const d = h("span", "dot");
        d.style.setProperty("--x", x(val(v)));
        d.dataset.tip = (v && v.who ? v.who + ": " : "") + fmt(val(v));
        track.appendChild(d);
      });
      if (r.mean !== undefined) {
        const m = h("span", "dot mean");
        m.style.setProperty("--x", x(r.mean));
        m.dataset.tip = r.label + ": mean " + fmt(r.mean);
        track.appendChild(m);
        const v = h("span", "val", fmt(r.mean));
        v.style.setProperty("--x", x(r.mean));
        track.appendChild(v);
      }
      plot.appendChild(track);
      said.push(r.label + ": " + (r.mean !== undefined ? "mean " + fmt(r.mean) + ", " : "") + (vs.length ? plural(vs.length, "value") + " from " + fmt(Math.min.apply(null, vs)) + " to " + fmt(Math.max.apply(null, vs)) : "no values"));
    });
    plot.appendChild(h("div"));
    const axis = h("div", "axis");
    ticks.forEach((t) => {
      const s = h("span", "", t);
      s.style.setProperty("--x", x(t));
      axis.appendChild(s);
    });
    plot.appendChild(axis);
    plot.setAttribute("role", "img");
    plot.setAttribute("aria-label", (opts.title ? opts.title + ". " : "") + "On a scale of " + opts.min + " to " + opts.max + ". " + said.join(". ") + "." + (opts.numbers === false ? "" : " The numbers are in the table below."));
    fig.appendChild(plot);
    if (opts.numbers === "all") {
      fig.appendChild(numbers(["", "Who", "Value"], rows.flatMap((r) => (r.values || []).map((v) => [r.label, (v && v.who) || "", fmt(val(v))]))));
    } else if (opts.numbers !== false) {
      fig.appendChild(numbers(["", "Mean", "Lowest", "Highest", "Values"], rows.map((r) => { const vs = (r.values || []).map(val); return [r.label, r.mean !== undefined ? fmt(r.mean) : "", vs.length ? fmt(Math.min.apply(null, vs)) : "", vs.length ? fmt(Math.max.apply(null, vs)) : "", vs.length]; })));
    }
    target.replaceChildren(fig);
    return fig;
  };

  /* ---------- Charts ----------
     Need Chart.js on the page, loaded in a script tag before this file, from
     https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js
     (No closing script tag is written anywhere in this file, so it can be inlined into a page.)
     Without it, each chart shows its numbers table instead. Every chart keeps that table in a fold under it,
     so no value is carried by colour alone and the figures survive a greyscale printout. */
  const stripes = (a, b) => {
    const c = document.createElement("canvas");
    c.width = c.height = 8;
    const x = c.getContext("2d");
    x.fillStyle = a; x.fillRect(0, 0, 8, 8);
    x.strokeStyle = b; x.lineWidth = 3; x.beginPath();
    x.moveTo(-2, 6); x.lineTo(6, -2); x.moveTo(2, 10); x.lineTo(10, 2); x.stroke();
    return x.createPattern(c, "repeat");
  };
  /* A part or a series takes its colour from its tone (a meaning); else from the palette, which is the series
     order by default ("neutral" for greys, or a list of tones). tone "both" is the striped mix of "for" and "against". */
  const paint = (item, i, palette) => {
    if (item.tone === "both") return stripes(css("--pp-s1"), css("--pp-s3"));
    if (TONES[item.tone]) return css(TONES[item.tone]);
    const list = palette === "neutral" ? NEUTRAL : Array.isArray(palette) ? palette : SERIES;
    return css(TONES[list[i % list.length]] || list[i % list.length]);
  };
  const charts = [];
  const mount = (target, o, height, build, table) => {
    const fig = figure(o);
    const wrap = h("div", "pp-canvas"), canvas = document.createElement("canvas");
    wrap.style.setProperty("--h", (o.height || height) + "px");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", (o.title || "Chart") + ". The numbers are in the table below.");
    wrap.appendChild(canvas); fig.appendChild(wrap); fig.appendChild(table);
    target.replaceChildren(fig);
    const entry = { chart: null, canvas };
    entry.draw = () => {
      if (!window.Chart) { wrap.hidden = true; table.open = true; return; }
      Chart.defaults.font.family = css("--pp-font-ui");
      Chart.defaults.font.size = 12;
      Chart.defaults.color = css("--pp-ink-2");
      Chart.defaults.animation = false;
      if (entry.chart) entry.chart.destroy();
      entry.chart = new Chart(canvas, build()); /* build() reads the tokens afresh, so a theme change or print recolours everything */
    };
    charts.push(entry);
    entry.draw();
    return fig;
  };
  const legend = () => ({ position: "bottom", labels: { boxWidth: 12, boxHeight: 12, padding: 14, color: css("--pp-ink") } });
  const axis = (grid, o) => Object.assign({ grid: { color: grid ? css("--pp-line") : "transparent", drawTicks: false }, border: { color: css("--pp-line-2") }, ticks: { color: css("--pp-ink-2"), padding: 6, precision: 0 } }, o || {});

  /* Each bar's value printed on the chart, so nobody has to hover: beside the bar, or inside a stacked segment
     when it fits. On by default in PP.columns and PP.stack; pass values: false to leave them off. */
  const VALUES = {
    id: "ppValues",
    afterDatasetsDraw(chart) {
      const ctx = chart.ctx, lying = chart.options.indexAxis === "y", stacked = !!chart.options.scales.x.stacked;
      const every = chart.data.datasets.flatMap((d) => d.data).filter((v) => typeof v === "number");
      const decimals = every.some((v) => v % 1 !== 0), signed = every.some((v) => v < 0);
      ctx.save();
      ctx.font = "500 11px " + css("--pp-font-ui");
      ctx.textBaseline = "middle";
      const ink = css("--pp-ink"), surface = css("--pp-surface");
      chart.data.datasets.forEach((d, i) => {
        const meta = chart.getDatasetMeta(i);
        if (meta.hidden) return;
        meta.data.forEach((bar, j) => {
          const v = d.data[j];
          if (typeof v !== "number") return;
          const text = (signed && v > 0 ? "+" : "") + (decimals ? v.toFixed(1) : v), w = ctx.measureText(text).width;
          const chip = (x, y) => { /* a small surface label, readable on any bar colour */
            ctx.fillStyle = surface;
            ctx.beginPath(); ctx.roundRect(x - w / 2 - 4, y - 8, w + 8, 16, 3); ctx.fill();
            ctx.fillStyle = ink; ctx.textAlign = "center"; ctx.fillText(text, x, y + 0.5);
          };
          if (stacked) {
            const size = Math.abs(lying ? bar.x - bar.base : bar.y - bar.base), x = lying ? (bar.x + bar.base) / 2 : bar.x, y = lying ? bar.y : (bar.y + bar.base) / 2;
            if (v && size >= w + 12) chip(x, y);
          } else if (lying) {
            const out = v < 0, x = out ? Math.min(bar.x, bar.base) - 6 : Math.max(bar.x, bar.base) + 6;
            ctx.fillStyle = ink; ctx.textAlign = out ? "right" : "left"; ctx.fillText(text, x, bar.y + 0.5);
          } else {
            const out = v < 0;
            ctx.fillStyle = ink; ctx.textAlign = "center"; ctx.fillText(text, bar.x, out ? bar.y + 9 : bar.y - 8);
          }
        });
      });
      ctx.restore();
    },
  };

  /* Donut or pie: parts of one whole, up to about five.
     o: {title, note, parts: [{label, n, tone}], centre: {value, label}, pie, palette, height, unit} */
  PP.donut = function (target, o) {
    const total = o.parts.reduce((a, b) => a + b.n, 0);
    const middle = {
      id: "ppCentre",
      afterDraw(chart) {
        if (o.pie || !o.centre) return;
        const { ctx, chartArea: a } = chart, x = (a.left + a.right) / 2, y = (a.top + a.bottom) / 2;
        ctx.save(); ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillStyle = css("--pp-ink"); ctx.font = "600 28px " + css("--pp-font-ui"); ctx.fillText(o.centre.value, x, y - 8);
        ctx.fillStyle = css("--pp-ink-2"); ctx.font = "12px " + css("--pp-font-ui"); ctx.fillText(o.centre.label || "", x, y + 16);
        ctx.restore();
      },
    };
    return mount(target, o, 240, () => ({
      type: "doughnut",
      data: { labels: o.parts.map((p) => p.label + "  " + p.n), datasets: [{ data: o.parts.map((p) => p.n), backgroundColor: o.parts.map((p, i) => paint(p, i, o.palette)), borderColor: css("--pp-surface"), borderWidth: 2, hoverOffset: 4 }] },
      options: { maintainAspectRatio: false, cutout: o.pie ? 0 : "62%", plugins: { legend: legend(), tooltip: { callbacks: { label: (c) => " " + o.parts[c.dataIndex].label + ": " + c.parsed + " of " + total } } } },
      plugins: [middle],
    }), numbers([o.unit || "Part", "Count"], o.parts.map((p) => [p.label, p.n]).concat([["All", total]])));
  };
  PP.pie = function (target, o) { return PP.donut(target, Object.assign({}, o, { pie: true })); };

  /* Bars, upright or lying down, side by side or stacked.
     o: {title, note, labels: [...], series: [{label, values: [...], tone}], stacked, horizontal, min, max, ticks, axisLabel,
         values (default true), palette, height, unit}
     A single series with no tone is neutral grey; several take the series order (or the palette). ticks is merged
     into the value axis's ticks, for example {stepSize: 1}. A label may be an array, drawn as two lines. */
  PP.columns = function (target, o) {
    const rows = o.labels.length, stacked = !!o.stacked, values = o.values !== false;
    const tall = o.horizontal ? Math.max(180, rows * (stacked ? 34 : 22 + 14 * o.series.length) + 70) : 280;
    const palette = o.palette || (o.series.length === 1 ? ["n2"] : undefined);
    return mount(target, o, tall, () => {
      const cat = axis(false, { stacked });
      const val = axis(true, { stacked, beginAtZero: o.min === undefined, min: o.min, max: o.max, title: o.axisLabel ? { display: true, text: o.axisLabel, color: css("--pp-ink-2") } : undefined });
      if (o.ticks) val.ticks = Object.assign(val.ticks, o.ticks);
      const room = values && !stacked ? (o.horizontal ? { right: 34, left: o.min < 0 ? 34 : 0 } : { top: 18 }) : {};
      return {
        type: "bar",
        data: { labels: o.labels, datasets: o.series.map((s, i) => ({ label: s.label, data: s.values, backgroundColor: paint(s, i, palette), borderColor: css("--pp-surface"), borderWidth: stacked ? 1 : 0, borderRadius: stacked ? 0 : 3, maxBarThickness: 30, categoryPercentage: 0.72, barPercentage: 0.9 })) },
        options: { maintainAspectRatio: false, indexAxis: o.horizontal ? "y" : "x", layout: { padding: room }, scales: o.horizontal ? { x: val, y: cat } : { x: cat, y: val }, plugins: { legend: Object.assign(legend(), { display: o.series.length > 1 }) } },
        plugins: values ? [VALUES] : [],
      };
    }, numbers([o.unit || ""].concat(o.series.map((s) => s.label)), o.labels.map((l, r) => [l].concat(o.series.map((s) => s.values[r])))));
  };
  PP.stack = function (target, o) { return PP.columns(target, Object.assign({ stacked: true, horizontal: true }, o)); };

  /* Radar: the shape of a few things across the same five to eight measures. o: {title, note, axes: [...], series: [{label, values, tone}], min, max, palette, height} */
  PP.radar = function (target, o) {
    const fade = (c) => { const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(c); return m ? "rgba(" + parseInt(m[1], 16) + "," + parseInt(m[2], 16) + "," + parseInt(m[3], 16) + ",0.14)" : c; };
    return mount(target, o, 340, () => ({
      type: "radar",
      data: { labels: o.axes, datasets: o.series.map((s, i) => { const c = paint(s, i, o.palette); return { label: s.label, data: s.values, borderColor: c, backgroundColor: typeof c === "string" ? fade(c) : c, borderWidth: 2, pointRadius: 3, pointBackgroundColor: c }; }) },
      options: { maintainAspectRatio: false, scales: { r: { min: o.min, max: o.max, grid: { color: css("--pp-line") }, angleLines: { color: css("--pp-line") }, pointLabels: { color: css("--pp-ink"), font: { size: 12 } }, ticks: { color: css("--pp-ink-3"), backdropColor: "transparent", precision: 0 } } }, plugins: { legend: legend() } },
    }), numbers([""].concat(o.series.map((s) => s.label)), o.axes.map((a, r) => [a].concat(o.series.map((s) => s.values[r])))));
  };

  /* ---------- The panel: who was simulated, what each model was told, and which models played them ----------
     o: {title, unit: "interview" | "run", open, palette (default "neutral"), told: ["what every participant was also told"],
         personas: [{id, name, role, segment (a name, not an id), trait, bio: [...]}],
         models: [{key, model, effort, harness or runner, role, job, runs}],
         runs: [{persona, model (a model's key), state, replicate}]}
     A model whose role is missing or "participant" plays personas, and its key heads a column of the matrix.
     Every other model (interviewer, analyst, critic, writer) is listed, not charted. kit.html shows how to build o from
     study.json and runs.json. A state is done, failed, limited, stopped, incomplete or not started. */
  const STATES = { done: ["yes", "finished"], failed: ["no", "failed"], limited: ["part", "stopped at a limit"], stopped: ["part", "stopped early"], incomplete: ["part", "did not finish"], "not started": ["na", "not started"] };
  const stateOf = (s) => STATES[s || "done"] || ["na", s];
  PP.panel = function (target, o) {
    const unit = o.unit || "run";
    const players = o.models.filter((m) => !m.role || m.role === "participant");
    const segments = Array.from(new Set(o.personas.map((p) => p.segment).filter(Boolean)));
    const fold = h("details", "pp-fold");
    fold.open = !!o.open;
    const sum = h("summary", "", o.title || "Who was on the panel");
    sum.appendChild(h("span", "count", plural(o.personas.length, "persona") + ", " + plural(players.length, "model") + ", " + plural(o.runs.length, unit)));
    fold.appendChild(sum);
    const body = h("div", "body");
    const stats = h("dl", "pp-stats");
    [[o.personas.length, "personas"], [segments.length, "segments"], [players.length, "models playing them"], [o.runs.length, unit + "s"]].forEach(([n, label]) => {
      if (label === "segments" && !n) return;
      const d = h("div", "pp-stat"); d.appendChild(h("dt", "", label)); d.appendChild(h("dd", "", n)); stats.appendChild(d);
    });
    body.appendChild(stats);
    const count = (key) => o.runs.filter((r) => r.model === key).length;
    const plots = h("div", "pp-grid two"), a = h("div"), b = h("div");
    const large = o.runs.length >= 6; /* a chart of two or three things says less than the table under it */
    if (large) { plots.appendChild(a); body.appendChild(plots); }
    /* Who ran on what: every run of every pairing, each with its state */
    const table = h("table", "pp-table"), hr = table.createTHead().insertRow();
    ["Persona"].concat(players.map((m) => m.key)).forEach((t, i) => { const th = h("th", i ? "c" : "", t); th.scope = "col"; hr.appendChild(th); });
    const tb = table.createTBody(), seen = {};
    o.personas.forEach((p) => {
      const tr = tb.insertRow(), th = h("th", "", p.name);
      th.scope = "row"; th.appendChild(h("span", "sub", p.role)); tr.appendChild(th);
      players.forEach((m) => {
        const mine = o.runs.filter((r) => r.persona === p.id && r.model === m.key).sort((x, y) => (x.replicate || 0) - (y.replicate || 0)), td = h("td", "c");
        mine.forEach((r) => (seen[r.state || "done"] = (seen[r.state || "done"] || 0) + 1));
        if (!mine.length) td.appendChild(sr("no " + unit));
        else if (mine.length <= 6) {
          const box = h("span", "pp-marks");
          mine.forEach((r, j) => {
            const [cls, word] = stateOf(r.state), mark = h("span", "pp-mark " + cls);
            mark.dataset.tip = p.name + " on " + m.key + (mine.length > 1 ? ", " + unit + " " + (r.replicate || j + 1) : "") + ": " + word;
            mark.tabIndex = 0; mark.appendChild(sr(mark.dataset.tip + ". ")); box.appendChild(mark);
          });
          td.appendChild(box);
        } else {
          const tally = {};
          mine.forEach((r) => { const w = stateOf(r.state)[1]; tally[w] = (tally[w] || 0) + 1; });
          td.appendChild(h("span", "pp-small", Object.keys(tally).map((w) => tally[w] + " " + w).join(", ")));
        }
        tr.appendChild(td);
      });
    });
    const scroll = h("div", "pp-scroll"); scroll.appendChild(table); body.appendChild(scroll);
    const key = h("ul", "pp-legend");
    Object.keys(seen).forEach((s) => { const [cls, word] = stateOf(s), li = h("li"); li.appendChild(h("span", "pp-mark " + cls)); li.appendChild(document.createTextNode(cap(word) + ", " + seen[s])); key.appendChild(li); });
    body.appendChild(key);
    if (o.told && o.told.length) {
      const c = h("div", "pp-callout"), ul = h("ul");
      c.appendChild(h("strong", "", "What every participant was also told"));
      o.told.forEach((line) => ul.appendChild(h("li", "", line)));
      c.appendChild(ul); body.appendChild(c);
    }
    const cards = h("div", "pp-grid");
    o.personas.forEach((p) => {
      const card = h("article", "pp-persona");
      card.appendChild(h("span", "pp-avatar", p.id)); card.appendChild(h("strong", "", p.name)); card.appendChild(h("p", "", p.role));
      if (p.trait) card.appendChild(h("p", "trait", p.trait));
      const chips = h("div", "pp-chips");
      if (p.segment) chips.appendChild(h("span", "pp-chip", p.segment));
      players.forEach((m) => { if (o.runs.some((r) => r.persona === p.id && r.model === m.key)) chips.appendChild(h("span", "pp-chip model", m.key)); });
      card.appendChild(chips);
      if (p.bio && p.bio.length) {
        const more = h("details", "pp-more"); more.appendChild(h("summary", "", "Background the model was given"));
        const ul = h("ul"); p.bio.forEach((line) => ul.appendChild(h("li", "", line))); more.appendChild(ul); card.appendChild(more);
      }
      cards.appendChild(card);
    });
    body.appendChild(cards);
    /* Every model: its name in the study, the exact model asked for (or the harness's configured default), its jobs */
    const mt = h("table", "pp-table"), mh = mt.createTHead().insertRow();
    ["Model", "Exact model", "Harness", "Job in this study", cap(unit) + "s played"].forEach((t, i) => { const th = h("th", i === 4 ? "n" : "", t); th.scope = "col"; mh.appendChild(th); });
    const mb = mt.createTBody();
    o.models.forEach((m) => {
      const tr = mb.insertRow(), th = h("th", "", m.key); th.scope = "row"; tr.appendChild(th);
      const id = tr.insertCell();
      id.appendChild(h("span", "pp-ref", m.model || "configured default"));
      if (m.effort) id.appendChild(h("span", "sub", "effort " + m.effort));
      const harness = tr.insertCell();
      harness.textContent = m.harness || m.runner || "";
      harness.style.whiteSpace = "nowrap";
      tr.insertCell().textContent = m.job || m.role || "participant";
      const player = !m.role || m.role === "participant";
      tr.appendChild(h("td", "n", m.runs !== undefined ? m.runs : player ? count(m.key) : ""));
    });
    const ms = h("div", "pp-scroll"); ms.appendChild(mt); body.appendChild(ms);
    fold.appendChild(body);
    target.replaceChildren(fold);
    const palette = o.palette || "neutral";
    if (large) PP.donut(a, { title: cap(unit) + "s by model", parts: players.map((m) => ({ label: m.key, n: count(m.key) })), centre: { value: o.runs.length, label: unit + "s" }, unit: "Model", palette });
    if (large && segments.length > 1) {
      plots.appendChild(b);
      PP.columns(b, { title: "Personas by segment", horizontal: true, labels: segments, series: [{ label: "Personas", values: segments.map((s) => o.personas.filter((p) => p.segment === s).length) }], palette: palette === "neutral" ? ["n2"] : palette, unit: "Segment", ticks: { stepSize: 1 } });
    }
    return fold;
  };

  /* A chart drawn inside a closed fold has no width yet: draw it again when its fold opens. */
  document.addEventListener("toggle", (e) => { if (e.target.open) charts.forEach((c) => { if (e.target.contains(c.canvas)) c.draw(); }); }, true);
  /* The canvases draw before the web fonts arrive: draw them again once the fonts are in. */
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => charts.forEach((c) => c.draw()));

  /* Paper: open every fold, draw every chart in the light colours, and put both back after printing. */
  let shut = [], kept = null, printing = false;
  const toPaper = () => {
    if (printing) return;
    printing = true;
    shut = Array.from(document.querySelectorAll("details:not([open])"));
    shut.forEach((d) => (d.open = true));
    kept = root.dataset.ppTheme || null;
    if (kept) delete root.dataset.ppTheme;
    charts.forEach((c) => c.draw());
  };
  const toScreen = () => {
    if (!printing) return;
    printing = false;
    shut.forEach((d) => (d.open = false));
    shut = [];
    if (kept) root.dataset.ppTheme = kept;
    kept = null;
    charts.forEach((c) => c.draw());
  };
  window.addEventListener("beforeprint", toPaper);
  window.addEventListener("afterprint", toScreen);
  const paper = window.matchMedia && window.matchMedia("print");
  if (paper && paper.addEventListener) paper.addEventListener("change", (e) => { if (e.matches) { toPaper(); charts.forEach((c) => c.chart && c.chart.resize()); } else toScreen(); });

  /* Theme: light unless the reader chose dark with the button, which is remembered on this device. */
  const stored = () => { try { return localStorage.getItem("pp-theme"); } catch (e) { return null; } };
  const setTheme = (dark) => {
    if (dark) root.dataset.ppTheme = "dark"; else delete root.dataset.ppTheme;
    try { localStorage.setItem("pp-theme", dark ? "dark" : "light"); } catch (e) { /* not remembered, still works */ }
    document.querySelectorAll(".pp-theme").forEach((b) => (b.textContent = dark ? "Light theme" : "Dark theme"));
    charts.forEach((c) => c.draw()); /* canvas colours are read from the tokens, so draw again */
  };
  if (stored() === "dark") root.dataset.ppTheme = "dark";
  const head = document.querySelector(".pp-head");
  if (head) {
    const b = h("button", "pp-theme", root.dataset.ppTheme === "dark" ? "Light theme" : "Dark theme");
    b.type = "button";
    b.id = "pp-theme-button";
    b.addEventListener("click", () => setTheme(root.dataset.ppTheme !== "dark"));
    head.appendChild(b);
  }

  /* Screenshots: any <button class="pp-zoom"> holding an <img> opens it full size, with its data-ref under it. */
  let box;
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".pp-zoom");
    if (btn) {
      const img = btn.querySelector("img");
      if (!img) return;
      if (!box) {
        box = h("dialog", "pp-lightbox");
        box.setAttribute("aria-label", "Screenshot, full size");
        const form = h("form"), close = h("button", "", "Close");
        form.method = "dialog";
        form.appendChild(h("p", "pp-ref")); form.appendChild(close);
        box.appendChild(h("img")); box.appendChild(form);
        (document.querySelector(".pp-page") || document.body).appendChild(box);
      }
      if (!box.showModal) return;
      const big = box.querySelector("img");
      big.src = img.currentSrc || img.src; big.alt = img.alt;
      box.querySelector("p").textContent = btn.dataset.ref || "";
      box.showModal();
      return;
    }
    if (box && (e.target === box || e.target === box.querySelector("img"))) box.close();
  });

  /* On this page: an empty <nav class="pp-toc"></nav> is filled with a link to each section that has an h2.
     A heading's data-toc gives a shorter link text. Built once the page's own scripts have run. */
  const contents = () => {
    document.querySelectorAll("nav.pp-toc").forEach((nav) => {
      if (nav.children.length) return;
      nav.setAttribute("aria-label", "On this page");
      nav.appendChild(h("span", "label", "On this page"));
      const used = new Set();
      document.querySelectorAll(".pp-section > h2").forEach((h2) => {
        const sec = h2.parentElement;
        if (!sec.id) {
          let id = "s-" + h2.textContent.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40), n = 2;
          while (used.has(id) || document.getElementById(id)) id = id.replace(/-\d+$/, "") + "-" + n++;
          sec.id = id;
        }
        used.add(sec.id);
        const a = h("a", "", h2.dataset.toc || h2.textContent);
        a.href = "#" + sec.id;
        nav.appendChild(a);
      });
    });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", contents); else contents();

  /* Copy buttons for snippets: <button data-copy="#id">. Falls back to selecting the text. */
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-copy]");
    if (!btn) return;
    const src = document.querySelector(btn.dataset.copy);
    if (!src) return;
    const done = () => { const was = btn.textContent; btn.textContent = "Copied"; setTimeout(() => (btn.textContent = was), 1400); };
    const select = () => { const r = document.createRange(); r.selectNodeContents(src); const s = getSelection(); s.removeAllRanges(); s.addRange(r); };
    try { navigator.clipboard.writeText(src.textContent).then(done, select); } catch (err) { select(); }
  });
})();
