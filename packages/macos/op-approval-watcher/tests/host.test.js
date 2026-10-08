// Compiles the macOS host's signal translation with HostTests.swift and runs
// it. macOS only; needs the Xcode Command Line Tools.
// Run from the repository root:
//   node --test packages/macos/op-approval-watcher/tests/
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { execFileSync, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const HOST = path.resolve(__dirname, "../.local/share/op-approval-watcher/host");

test("the host turns window, input and log changes into the events the engine expects", { skip: process.platform !== "darwin" }, (t) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "opa-host-"));
    t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
    fs.copyFileSync(path.join(__dirname, "HostTests.swift"), path.join(dir, "main.swift"));
    const binary = path.join(dir, "host-tests");
    execFileSync("xcrun", ["swiftc", "-swift-version", "5", "-o", binary, path.join(dir, "main.swift"), path.join(HOST, "Signals.swift")],
        { stdio: ["ignore", "ignore", "pipe"] });
    const run = spawnSync(binary, { encoding: "utf8" });
    assert.equal(run.status, 0, run.stdout + run.stderr);
    assert.equal(run.stdout.trim(), "ok");
});
