// The `op` admission window of the requesters helper (D3), run for real
// against a stand-in `op` process. Linux only.
// Run from the repository root:
//   node --test packages/omarchy/op-approval-watcher/tests/
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { execFileSync, spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const REQUESTERS = path.resolve(__dirname, "../.local/share/op-approval-watcher/requesters");

function opPids(home, openedAtMs) {
    const out = execFileSync(REQUESTERS, ["--opened-at", (openedAtMs / 1000).toFixed(3)], {
        env: { PATH: process.env.PATH, HOME: home },
        encoding: "utf8"
    });
    return JSON.parse(out).candidates.filter(c => c.source === "op").map(c => c.pid);
}

test("an op process counts only if it started no later than the window and at most 5 s before", { skip: process.platform !== "linux" }, async (t) => {
    const home = fs.mkdtempSync(path.join(os.tmpdir(), "opa-requesters-test-"));
    // A process whose comm is "op": a copy of sleep under that name.
    const op = path.join(home, "op");
    fs.copyFileSync("/usr/bin/sleep", op);
    fs.chmodSync(op, 0o755);
    const before = Date.now();
    const child = spawn(op, ["30"], { stdio: "ignore" });
    t.after(() => {
        child.kill();
        fs.rmSync(home, { recursive: true, force: true });
    });
    while (!fs.existsSync(`/proc/${child.pid}/comm`) || fs.readFileSync(`/proc/${child.pid}/comm`, "utf8").trim() !== "op")
        await new Promise(r => setTimeout(r, 10));
    const after = Date.now();

    assert.ok(opPids(home, after + 500).includes(child.pid), "started shortly before the window");
    assert.ok(!opPids(home, before - 100).includes(child.pid), "started after the window opened");
    assert.ok(!opPids(home, after + 5_500).includes(child.pid), "started more than 5 s before the window");
});
