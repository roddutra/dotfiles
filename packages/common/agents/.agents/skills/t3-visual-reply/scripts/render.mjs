#!/usr/bin/env node
// Builds a T3 Code visual reply from a JSON payload of blocks.
// Usage: node render.mjs [payload.json] > page.html   (reads stdin when no file is given)
// Invalid input exits 1 with every problem listed on stderr.

import { readFileSync } from "node:fs";

const SCHEMA_VERSION = 1;
const TONES = ["neutral", "info", "success", "warning", "danger"];
const MAX_DEPTH = 3;
const errors = [];

const fail = (path, message) => errors.push(`${path}: ${message}`);

const esc = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

// Escapes first, then allows `code`, **bold** and [label](https://url) only.
function inline(value) {
  const codes = [];
  let out = esc(value).replace(/`([^`]+)`/g, (_, code) => {
    codes.push(`<code>${code}</code>`);
    return `\u0000${codes.length - 1}\u0000`;
  });
  out = out
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  return out.replace(/\u0000(\d+)\u0000/g, (_, i) => codes[Number(i)]);
}

const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

function str(obj, key, path, { required = true } = {}) {
  const v = obj[key];
  if (v === undefined || v === null || v === "") {
    if (required) fail(`${path}.${key}`, "is required");
    return undefined;
  }
  if (typeof v !== "string") {
    fail(`${path}.${key}`, "must be a string");
    return undefined;
  }
  return v;
}

function strList(obj, key, path, { required = false } = {}) {
  const v = obj[key];
  if (v === undefined) {
    if (required) fail(`${path}.${key}`, "is required");
    return [];
  }
  if (!Array.isArray(v) || v.some((x) => typeof x !== "string" || x === "")) {
    fail(`${path}.${key}`, "must be an array of non-empty strings");
    return [];
  }
  return v;
}

function arr(obj, key, path, { min = 1 } = {}) {
  const v = obj[key];
  if (!Array.isArray(v) || v.length < min) {
    fail(`${path}.${key}`, `must be an array with at least ${min} item${min === 1 ? "" : "s"}`);
    return [];
  }
  return v;
}

function tone(obj, path, fallback = "neutral") {
  const v = obj.tone ?? fallback;
  if (!TONES.includes(v)) fail(`${path}.tone`, `must be one of ${TONES.join(", ")}`);
  return TONES.includes(v) ? v : fallback;
}

function allowKeys(obj, keys, path) {
  for (const k of Object.keys(obj)) if (!keys.includes(k)) fail(`${path}.${k}`, "is not a known field");
}

const bullets = (items) => (items.length ? `<ul>${items.map((i) => `<li>${inline(i)}</li>`).join("")}</ul>` : "");

const BLOCKS = {
  lede(b, p) {
    allowKeys(b, ["type", "text", "sub"], p);
    const text = str(b, "text", p);
    const sub = str(b, "sub", p, { required: false });
    return `<header class="v-lede"><p class="v-lede-text">${inline(text ?? "")}</p>${sub ? `<p class="v-muted">${inline(sub)}</p>` : ""}</header>`;
  },

  heading(b, p) {
    allowKeys(b, ["type", "text"], p);
    return `<h2 class="v-h">${inline(str(b, "text", p) ?? "")}</h2>`;
  },

  text(b, p) {
    allowKeys(b, ["type", "text", "muted"], p);
    return `<p class="v-p${b.muted ? " v-muted" : ""}">${inline(str(b, "text", p) ?? "")}</p>`;
  },

  list(b, p) {
    allowKeys(b, ["type", "items", "ordered"], p);
    const items = strList(b, "items", p, { required: true });
    const tag = b.ordered ? "ol" : "ul";
    return `<${tag} class="v-list">${items.map((i) => `<li>${inline(i)}</li>`).join("")}</${tag}>`;
  },

  callout(b, p) {
    allowKeys(b, ["type", "tone", "title", "text", "items"], p);
    const t = tone(b, p, "info");
    const title = str(b, "title", p, { required: false });
    const text = str(b, "text", p, { required: !b.items });
    return `<div class="v-callout v-tone-${t}">${title ? `<p class="v-callout-title">${inline(title)}</p>` : ""}${text ? `<p>${inline(text)}</p>` : ""}${bullets(strList(b, "items", p))}</div>`;
  },

  facts(b, p) {
    allowKeys(b, ["type", "items"], p);
    const rows = arr(b, "items", p).map((it, i) => {
      const ip = `${p}.items[${i}]`;
      if (!isObj(it)) return fail(ip, "must be an object"), "";
      allowKeys(it, ["label", "value"], ip);
      return `<div class="v-fact"><dt>${inline(str(it, "label", ip) ?? "")}</dt><dd>${inline(str(it, "value", ip) ?? "")}</dd></div>`;
    });
    return `<dl class="v-facts">${rows.join("")}</dl>`;
  },

  cards(b, p) {
    allowKeys(b, ["type", "items"], p);
    const items = arr(b, "items", p);
    const cards = items.map((it, i) => {
      const ip = `${p}.items[${i}]`;
      if (!isObj(it)) return fail(ip, "must be an object"), "";
      allowKeys(it, ["title", "tag", "tone", "text", "items", "highlight"], ip);
      const t = tone(it, ip);
      const tag = str(it, "tag", ip, { required: false });
      const text = str(it, "text", ip, { required: false });
      return `<div class="v-box v-card${it.highlight ? ` v-hl v-tone-${t}` : ""}">${tag ? `<span class="v-tag v-tone-${t}">${inline(tag)}</span>` : ""}<h3>${inline(str(it, "title", ip) ?? "")}</h3>${text ? `<p>${inline(text)}</p>` : ""}${bullets(strList(it, "items", ip))}</div>`;
    });
    return `<div class="v-grid v-cols-${Math.min(items.length, 3)}">${cards.join("")}</div>`;
  },

  steps(b, p) {
    allowKeys(b, ["type", "items"], p);
    const steps = arr(b, "items", p).map((it, i) => {
      const ip = `${p}.items[${i}]`;
      if (!isObj(it)) return fail(ip, "must be an object"), "";
      allowKeys(it, ["title", "text"], ip);
      const text = str(it, "text", ip, { required: false });
      return `<li class="v-box v-step"><span class="v-step-n">${i + 1}</span><div><b>${inline(str(it, "title", ip) ?? "")}</b>${text ? `<p>${inline(text)}</p>` : ""}</div></li>`;
    });
    return `<ol class="v-steps">${steps.join("")}</ol>`;
  },

  table(b, p) {
    allowKeys(b, ["type", "columns", "rows", "caption"], p);
    const cols = strList(b, "columns", p, { required: true });
    const rows = arr(b, "rows", p).map((row, i) => {
      if (!Array.isArray(row) || row.length !== cols.length || row.some((c) => typeof c !== "string")) {
        fail(`${p}.rows[${i}]`, `must be an array of ${cols.length} strings`);
        return "";
      }
      return `<tr>${row.map((c, j) => (j === 0 ? `<th scope="row">${inline(c)}</th>` : `<td>${inline(c)}</td>`)).join("")}</tr>`;
    });
    const caption = str(b, "caption", p, { required: false });
    return `<div class="v-table-wrap"><table class="v-table">${caption ? `<caption>${inline(caption)}</caption>` : ""}<thead><tr>${cols.map((c) => `<th scope="col">${inline(c)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
  },

  code(b, p) {
    allowKeys(b, ["type", "code", "caption"], p);
    const caption = str(b, "caption", p, { required: false });
    return `<figure class="v-code">${caption ? `<figcaption>${inline(caption)}</figcaption>` : ""}<pre><code>${esc(str(b, "code", p) ?? "")}</code></pre></figure>`;
  },

  decision(b, p) {
    allowKeys(b, ["type", "question", "required", "recommended", "options", "context"], p);
    const question = str(b, "question", p);
    const context = str(b, "context", p, { required: false });
    const required = b.required !== false;
    const options = arr(b, "options", p, { min: 2 });
    if (options.length > 4) fail(`${p}.options`, "must have at most 4 options");
    const ids = new Set();
    const html = options.map((o, i) => {
      const ip = `${p}.options[${i}]`;
      if (!isObj(o)) return fail(ip, "must be an object"), "";
      allowKeys(o, ["id", "label", "summary", "pros", "cons"], ip);
      const id = str(o, "id", ip);
      if (id !== undefined && !/^[a-z0-9][a-z0-9 +-]{0,23}$/.test(id)) fail(`${ip}.id`, "must be a short lowercase reply token (a-z, 0-9, space, + or -)");
      if (id !== undefined && ids.has(id)) fail(`${ip}.id`, `duplicates "${id}"`);
      ids.add(id);
      const rec = id !== undefined && id === b.recommended;
      const summary = str(o, "summary", ip, { required: false });
      const pros = strList(o, "pros", ip).map((x) => `<li class="v-pro">${inline(x)}</li>`);
      const cons = strList(o, "cons", ip).map((x) => `<li class="v-con">${inline(x)}</li>`);
      return `<div class="v-opt${rec ? " v-rec" : ""}"><div class="v-opt-body"><h3>${inline(str(o, "label", ip) ?? "")}${rec ? ' <span class="v-rec-tag">Recommended</span>' : ""}</h3>${summary ? `<p>${inline(summary)}</p>` : ""}${pros.length || cons.length ? `<ul class="v-pc">${pros.join("")}${cons.join("")}</ul>` : ""}</div><div class="v-reply">reply <code>${esc(id ?? "")}</code></div></div>`;
    });
    if (b.recommended !== undefined && !ids.has(b.recommended)) fail(`${p}.recommended`, "must match an option id");
    const pill = required ? '<span class="v-pill v-tone-danger">Needs your choice</span>' : '<span class="v-pill v-tone-warning">Optional, your call</span>';
    const layout = options.length === 2 ? "v-opts-2" : "v-opts-rows";
    return `<section class="v-decision">${pill}<h2 class="v-q">${inline(question ?? "")}</h2>${context ? `<p class="v-muted">${inline(context)}</p>` : ""}<div class="v-opts ${layout}">${html.join("")}</div></section>`;
  },

  status(b, p) {
    allowKeys(b, ["type", "title", "source", "as_of", "done", "working", "next", "waiting"], p);
    const title = str(b, "title", p);
    const source = str(b, "source", p);
    const asOf = str(b, "as_of", p);
    const done = strList(b, "done", p);
    const working = strList(b, "working", p);
    const next = strList(b, "next", p);
    const waiting = arr(b, "waiting", p, { min: 0 }).map((w, i) => {
      const ip = `${p}.waiting[${i}]`;
      if (typeof w === "string" && w) return { text: w };
      if (isObj(w)) {
        allowKeys(w, ["text", "on"], ip);
        return { text: str(w, "text", ip) ?? "", on: str(w, "on", ip, { required: false }) };
      }
      fail(ip, "must be a string or { text, on }");
      return { text: "" };
    });
    if (b.waiting === undefined) errors.pop();
    const total = done.length + working.length + next.length + waiting.length;
    if (total === 0) fail(p, "needs at least one item in done, working, next or waiting");
    const seg = (n, cls) => (n ? `<span class="${cls}" style="flex:${n}"></span>` : "");
    const group = (label, items, cls) => (items.length ? `<div class="v-sgroup"><p class="v-slabel${cls ? ` ${cls}` : ""}">${label}</p><ul>${items.join("")}</ul></div>` : "");
    return `<section class="v-box v-status">
<div class="v-status-head"><h2 class="v-h">${inline(title ?? "")}</h2><span class="v-count">${done.length} / ${total} done</span></div>
<div class="v-bar" role="img" aria-label="${done.length} of ${total} done">${seg(done.length, "v-seg-done")}${seg(working.length, "v-seg-working")}${seg(next.length + waiting.length, "v-seg-rest")}</div>
${group("Working on", working.map((x) => `<li>${inline(x)}</li>`), "v-c-working")}
${group("Next", next.map((x) => `<li>${inline(x)}</li>`), "")}
${group("Waiting", waiting.map((w) => `<li>${inline(w.text)}${w.on ? ` <span class="v-muted">waits on ${inline(w.on)}</span>` : ""}</li>`), "v-c-waiting")}
${done.length ? `<details class="v-done"><summary>${done.length} done</summary><ul>${done.map((x) => `<li>${inline(x)}</li>`).join("")}</ul></details>` : ""}
<p class="v-snapshot">Snapshot from ${inline(source ?? "")}, ${inline(asOf ?? "")}</p>
</section>`;
  },

  details(b, p, depth) {
    allowKeys(b, ["type", "summary", "blocks", "open"], p);
    const summary = str(b, "summary", p);
    const inner = renderBlocks(arr(b, "blocks", p), `${p}.blocks`, depth + 1);
    return `<details class="v-details"${b.open ? " open" : ""}><summary>${inline(summary ?? "")}</summary><div class="v-stack">${inner}</div></details>`;
  },

  // Escape hatch for content the kit does not cover. Inserted unescaped.
  html(b, p) {
    allowKeys(b, ["type", "html", "css"], p);
    const html = str(b, "html", p) ?? "";
    const css = str(b, "css", p, { required: false }) ?? "";
    const both = `${html}\n${css}`;
    if (/\d(\.\d+)?[sld]?vh\b/i.test(both)) fail(p, "must not use vh units (T3 rejects them)");
    if (/<(html|head|body)[\s>]/i.test(html)) fail(`${p}.html`, "must be a fragment, not a full document");
    if (/(src|href)\s*=\s*["']?\s*(https?:)?\/\//i.test(html) || /url\(\s*["']?(https?:)?\/\//i.test(both) || /@import/i.test(css))
      fail(p, "must not load remote resources");
    return `${css ? `<style>${css.replace(/<\/style/gi, "<\\/style")}</style>` : ""}<div class="v-raw">${html}</div>`;
  },
};

function renderBlocks(blocks, path, depth) {
  if (depth > MAX_DEPTH) {
    fail(path, `nesting is limited to ${MAX_DEPTH} levels`);
    return "";
  }
  return blocks
    .map((b, i) => {
      const p = `${path}[${i}]`;
      if (!isObj(b)) return fail(p, "must be an object"), "";
      const fn = BLOCKS[b.type];
      if (!fn) return fail(`${p}.type`, `unknown block type ${JSON.stringify(b.type)}; expected one of ${Object.keys(BLOCKS).join(", ")}`), "";
      return fn(b, p, depth);
    })
    .join("\n");
}

const CSS = `
:root{--v-muted:var(--muted-foreground);--v-gap:14px}
*{box-sizing:border-box}
.v-stack{display:flex;flex-direction:column;gap:var(--v-gap)}
.v-stack>*{margin:0}
p{margin:0}
code{font-family:var(--font-mono);font-size:.88em;background:color-mix(in oklab,var(--foreground) 10%,transparent);padding:1px 4px;border-radius:4px}
a{color:var(--primary)}
.v-muted{color:var(--v-muted)}
.v-lede-text{font-size:17px;font-weight:600;line-height:1.35}
.v-lede .v-muted{font-size:13.5px;line-height:1.5;margin-top:4px}
.v-h{font-size:15px;font-weight:600;margin:0}
.v-p{font-size:14px;line-height:1.55}
.v-list{margin:0;padding-left:20px;font-size:14px;line-height:1.55}
.v-box{background:var(--card);color:var(--card-foreground);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px}
.v-tone-neutral{--v-tone:var(--v-muted)}
.v-tone-info{--v-tone:var(--info)}
.v-tone-success{--v-tone:var(--success)}
.v-tone-warning{--v-tone:var(--warning)}
.v-tone-danger{--v-tone:var(--destructive)}
.v-callout{border:1px solid color-mix(in oklab,var(--v-tone) 45%,var(--border));border-left:3px solid var(--v-tone);background:color-mix(in oklab,var(--v-tone) 9%,transparent);border-radius:var(--radius);padding:12px 16px;font-size:13.5px;line-height:1.5}
.v-callout-title{font-weight:600;margin-bottom:2px}
.v-callout ul{margin:4px 0 0;padding-left:18px}
.v-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:0}
.v-fact{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:10px 14px}
.v-fact dt{font-size:12px;color:var(--v-muted)}
.v-fact dd{margin:2px 0 0;font-size:15px;font-weight:600;font-variant-numeric:tabular-nums}
.v-grid{display:grid;gap:10px}
.v-cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}
.v-cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}
.v-card h3{font-size:14px;margin:0 0 4px}
.v-card p,.v-card li{font-size:12.5px;line-height:1.45;color:var(--v-muted)}
.v-card ul{margin:6px 0 0;padding-left:16px}
.v-card p+ul,.v-card ul+p{margin-top:6px}
.v-hl{border-color:var(--v-tone);box-shadow:0 0 0 1px var(--v-tone)}
.v-tag,.v-pill{display:inline-block;font-size:11px;font-weight:600;line-height:1.4;padding:2px 8px;border-radius:999px;color:var(--v-tone);border:1px solid color-mix(in oklab,var(--v-tone) 55%,transparent);background:color-mix(in oklab,var(--v-tone) 12%,transparent)}
.v-tag{margin-bottom:6px}
.v-steps{list-style:none;margin:0;padding:0;display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.v-step{display:flex;gap:10px;padding:10px 12px}
.v-step-n{flex:none;width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:600;background:color-mix(in oklab,var(--primary) 18%,transparent);color:var(--foreground);font-variant-numeric:tabular-nums}
.v-step b{font-size:13px}
.v-step p{font-size:12.5px;line-height:1.45;color:var(--v-muted);margin-top:2px}
.v-table-wrap{overflow-x:auto;border:1px solid var(--border);border-radius:var(--radius)}
.v-table{border-collapse:collapse;width:100%;font-size:13px}
.v-table caption{text-align:left;padding:8px 12px;color:var(--v-muted);font-size:12px}
.v-table th,.v-table td{text-align:left;vertical-align:top;padding:8px 12px;border-top:1px solid var(--border);line-height:1.45}
.v-table thead th{border-top:0;background:var(--muted);color:var(--muted-foreground);font-weight:600;font-size:12px}
.v-table tbody th{font-weight:600}
.v-code{margin:0}
.v-code figcaption{font-size:12px;color:var(--v-muted);margin-bottom:4px}
.v-code pre{margin:0;padding:12px 14px;background:var(--code-background);border:1px solid var(--border);border-radius:var(--radius);overflow-x:auto;font-size:12.5px;line-height:1.5}
.v-code pre code{background:none;padding:0;font-size:inherit}
.v-decision{display:flex;flex-direction:column;gap:8px;align-items:flex-start}
.v-decision>.v-opts{align-self:stretch;margin-top:4px}
.v-q{font-size:16px;font-weight:600;line-height:1.35;margin:0}
.v-decision>.v-muted{font-size:13.5px;line-height:1.5}
.v-opts{display:grid;gap:10px}
.v-opts-2{grid-template-columns:repeat(2,minmax(0,1fr))}
.v-opts-rows{grid-template-columns:1fr}
.v-opts-rows .v-opt{flex-direction:row}
.v-opts-rows .v-reply{border-top:0;border-left:1px solid var(--border);display:flex;align-items:center;gap:6px;flex:none;min-width:120px}
.v-opts-rows .v-rec .v-reply{border-left-color:color-mix(in oklab,var(--success) 60%,transparent)}
.v-opt{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);display:flex;flex-direction:column;overflow:hidden}
.v-opt-body{padding:12px 16px;flex:1}
.v-opt h3{font-size:14.5px;margin:0 0 4px;display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.v-opt p{font-size:13px;line-height:1.45;color:var(--v-muted)}
.v-pc{list-style:none;margin:6px 0 0;padding:0;font-size:12.5px;line-height:1.45;display:flex;flex-direction:column;gap:3px}
.v-pc li{padding-left:18px;position:relative;color:var(--v-muted)}
.v-pc li::before{position:absolute;left:0;font-weight:700}
.v-pro::before{content:"+";color:var(--success)}
.v-con::before{content:"\\2212";color:var(--destructive)}
.v-reply{font-size:12px;padding:7px 16px;border-top:1px solid var(--border);color:var(--v-muted)}
.v-rec{border-color:var(--success);box-shadow:0 0 0 1px var(--success)}
.v-rec .v-reply{background:color-mix(in oklab,var(--success) 16%,transparent);border-top-color:color-mix(in oklab,var(--success) 60%,transparent);color:var(--foreground)}
.v-rec-tag{font-size:11px;font-weight:600;color:var(--success)}
.v-status{display:flex;flex-direction:column;gap:10px}
.v-status-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
.v-count{font-size:13px;font-weight:600;font-variant-numeric:tabular-nums}
.v-bar{display:flex;gap:3px;height:8px}
.v-bar span{border-radius:999px}
.v-seg-done{background:var(--success)}
.v-seg-working{background:var(--info)}
.v-seg-rest{background:color-mix(in oklab,var(--foreground) 14%,transparent)}
.v-sgroup ul{margin:2px 0 0;padding-left:18px;font-size:13px;line-height:1.5}
.v-slabel{font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--v-muted)}
.v-c-working{color:var(--info)}
.v-c-waiting{color:var(--warning)}
.v-done summary{font-size:13px;color:var(--v-muted);cursor:pointer}
.v-done ul{margin:4px 0 0;padding-left:18px;font-size:13px;line-height:1.5;color:var(--v-muted)}
.v-snapshot{font-size:11.5px;color:var(--v-muted);border-top:1px solid var(--border);padding-top:8px}
.v-details{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:10px 16px}
.v-details>summary{cursor:pointer;font-weight:600;font-size:13.5px}
.v-details[open]>summary{margin-bottom:10px}
summary:focus-visible{outline:2px solid var(--ring);outline-offset:2px;border-radius:4px}
@media (max-width:540px){.v-cols-2,.v-cols-3,.v-opts-2{grid-template-columns:1fr}.v-opts-rows .v-opt{flex-direction:column}.v-opts-rows .v-reply{border-left:0;border-top:1px solid var(--border)}}
`;

function main() {
  const file = process.argv[2];
  let raw;
  try {
    raw = readFileSync(file ?? 0, "utf8");
  } catch (e) {
    console.error(`Cannot read ${file ?? "stdin"}: ${e.message}`);
    process.exit(1);
  }
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (e) {
    console.error(`Invalid JSON: ${e.message}`);
    process.exit(1);
  }
  if (!isObj(payload)) {
    console.error("Payload must be a JSON object");
    process.exit(1);
  }
  allowKeys(payload, ["schema_version", "title", "blocks"], "$");
  if (payload.schema_version !== SCHEMA_VERSION) fail("$.schema_version", `must be ${SCHEMA_VERSION}`);
  const title = str(payload, "title", "$");
  if (title && title.length > 200) fail("$.title", "must be 200 characters or fewer");
  const body = renderBlocks(arr(payload, "blocks", "$"), "$.blocks", 1);
  const html = `<!doctype html>
<html lang="en-AU"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title ?? "")}</title>
<style>${CSS}</style></head>
<body><main class="v-stack">
${body}
</main></body></html>
`;
  if (/[\u2013\u2014]/.test(html)) fail("$", "contains an en or em dash; use a comma, colon, parentheses or a hyphen");
  if (html.length > 512000) fail("$", `renders to ${html.length} characters; html_render accepts at most 512000`);
  if (errors.length) {
    console.error(`Invalid payload (${errors.length} problem${errors.length === 1 ? "" : "s"}):`);
    for (const e of errors) console.error(`  ${e}`);
    process.exit(1);
  }
  process.stdout.write(html);
}

main();
