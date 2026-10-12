// Guard for the persona-panel skill's Pi runner. scripts/runners/pi.py owns this file and loads
// it into every run with `-e <this file> --panel-guard files|browse`. Nothing else uses it.
//
// Pi has no sandbox and asks for no approval, so this is what confines a run:
//
// - read, write, edit, grep, find, ls: the path Pi will open must be inside the working directory.
//   Pi rewrites a path argument before it opens it, so the guard takes the same steps in the same
//   order (opened() below, copied from pi 1.1.0), follows every symbolic link, and hands Pi the
//   absolute path it checked. It refuses a path those steps would change again, because Pi takes
//   them once more on what it is handed: a path with a Unicode space that a file:// URL decodes
//   to, and every path when the working directory's own path holds one. It refuses a control
//   character anywhere in the path, a link that leads nowhere, and each other spelling of a
//   missing file that Pi's read tool would try. No other argument of these tools names a file.
// - grep's glob and find's pattern: no absolute pattern and no ".." part. Both only filter what
//   is under the path, and neither tool follows a symbolic link it finds there.
// - bash: refused, unless the run was launched with `--panel-guard browse`. Then one
//   agent-browser command is allowed and nothing else: no second command, pipe, redirection,
//   substitution, variable or assignment. Its arguments are plain words or quoted text.
// - any other tool: refused.
//
// It fails closed. Only this file defines --panel-guard, so Pi refuses to start when the file
// is missing or cannot be loaded, and Pi blocks a tool call whose check throws.
//
// Not covered: what agent-browser itself opens or saves, a link swapped in between the check
// and the use, and hard links.

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const FLAG = "panel-guard";
const FILE_TOOLS = new Set(["read", "write", "edit", "grep", "find", "ls"]);
const PATTERNS: Record<string, string> = { grep: "glob", find: "pattern" };
const UNICODE_SPACES = /[\u00A0\u2000-\u200A\u202F\u205F\u3000]/g;
const CONTROL = /[\x00-\x1f\x7f]/;
// A word of characters the shell leaves alone, or quoted text in which nothing is special.
const WORD = "(?:[A-Za-z0-9_@%+=:,./?#~-]+|'[^']*'|\"[^\"$`\\\\]*\")+";
const BROWSER_COMMAND = new RegExp(`^agent-browser(?: +${WORD})*$`);
const SHELL_REFUSAL =
  "Only one agent-browser command is allowed, with no chaining, pipes, redirection, substitution or " +
  "variables. Put an argument that holds other characters in single quotes";

// The path Pi's file tools open for a path argument: its own steps, in its order. Unicode spaces
// become spaces, one leading "@" is dropped, then "~" is the home directory or else a file://
// URL is decoded, and what is left is resolved against the working directory.
function opened(root: string, given: string): string {
  let p = given.replace(UNICODE_SPACES, " ");
  if (p.startsWith("@")) p = p.slice(1);
  if (p === "~") p = os.homedir();
  else if (p.startsWith("~/")) p = path.join(os.homedir(), p.slice(2));
  else if (/^file:\/\//.test(p)) p = fileURLToPath(p);
  return path.resolve(root, p);
}

// The same path with every symbolic link followed. A part that does not exist yet is kept as
// written. null for a link that cannot be followed.
function real(p: string): string | null {
  try {
    return fs.realpathSync(p);
  } catch {
    let link = false;
    try {
      link = fs.lstatSync(p).isSymbolicLink();
    } catch {}
    const parent = path.dirname(p);
    if (link || parent === p) return null;
    const above = real(parent);
    return above === null ? null : path.join(above, path.basename(p));
  }
}

// The spellings of a missing file that Pi's read tool tries in turn, opened as they are.
function spellings(p: string): string[] {
  const nfd = p.normalize("NFD");
  const curly = (s: string) => s.replace(/'/g, "\u2019");
  return [p, p.replace(/ (AM|PM)\./gi, "\u202F$1."), nfd, curly(p), curly(nfd)];
}

function inside(root: string, p: string): boolean {
  const followed = real(p);
  return followed !== null && (followed === root || followed.startsWith(root + path.sep));
}

export default function (pi: any) {
  pi.registerFlag(FLAG, { description: "Persona panel guard: files or browse", type: "string" });

  pi.on("tool_call", async (event: any, ctx: any) => {
    const refuse = (reason: string) => ({ block: true, reason });
    const input = event.input ?? {};
    if (FILE_TOOLS.has(event.toolName)) {
      const root = fs.realpathSync(ctx.cwd);
      const given = input.path ?? ".";
      if (typeof given !== "string") return refuse("The path must be text");
      const full = opened(root, given);
      if (CONTROL.test(given + full) || opened(root, full) !== full) {
        return refuse(`Path "${given}" is refused: write it with plain characters, with no control ` +
          "character and no space other than an ordinary one");
      }
      if (!spellings(full).every((p) => inside(root, p))) {
        return refuse(`Path "${given}" is outside the working directory`);
      }
      const pattern = input[PATTERNS[event.toolName]];
      if (typeof pattern === "string" && (path.isAbsolute(pattern) || pattern.split(/[\\/]/).includes(".."))) {
        return refuse(`Pattern "${pattern}" reaches outside the working directory`);
      }
      if (input.path != null) input.path = full;
      return undefined;
    }
    if (event.toolName === "bash" && pi.getFlag(FLAG) === "browse") {
      const command = String(input.command ?? "").trim();
      if (CONTROL.test(command) || !BROWSER_COMMAND.test(command)) return refuse(SHELL_REFUSAL);
      input.command = command;
      return undefined;
    }
    return refuse(`The ${event.toolName} tool is not available in this run`);
  });
}
