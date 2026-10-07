// Decision table of the 1Password approval watcher (Policy.js).
// Run from the repository root:
//   node --test packages/omarchy/op-approval-watcher/tests/
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const P = require("../.local/share/op-approval-watcher/Policy.js");

const LIB = path.resolve(__dirname, "../../agents/.agents/lib/op-approval");

function config(overrides) {
    const c = P.defaults();
    for (const [section, values] of Object.entries(overrides || {}))
        Object.assign(c[section], values);
    return c;
}

const OPEN = 1_791_000_000_000;
const CLOSED = OPEN + 59_800;
const EXPIRED_AT = Math.floor(CLOSED / 1000);

test("window events keep commas in titles and match addresses across 0x prefixes", () => {
    assert.deepEqual(P.parseWindowEvent("openwindow", "5b3b90c58a40,7,com.onepassword.OnePassword,a, b, c"), {
        type: "open", address: "5b3b90c58a40", workspace: "7", windowClass: "com.onepassword.OnePassword", title: "a, b, c"
    });
    assert.deepEqual(P.parseWindowEvent("windowtitlev2", "5B3B90C58A40,x, y"), { type: "title", address: "5b3b90c58a40", title: "x, y" });
    assert.deepEqual(P.parseWindowEvent("closewindow", "5b3b90c58a40"), { type: "close", address: "5b3b90c58a40" });
    assert.equal(P.parseWindowEvent("openlayer", "omarchy-polkit"), null);
    assert.equal(P.addressKey("0x5b3b90c58a40"), P.parseWindowEvent("closewindow", "5b3b90c58a40").address);
});

test("a window is confirmed only while open, untouched, of the 1Password class and titled exactly 1Password", () => {
    const candidate = { address: "5b3b90c58a40", closed: false, titleChanged: false };
    const client = { address: "0x5b3b90c58a40", class: "com.onepassword.OnePassword", title: "1Password" };
    const cases = [
        ["approval window", candidate, [client], true],
        ["closed before the check", { ...candidate, closed: true }, [client], false],
        ["title changed after opening", { ...candidate, titleChanged: true }, [client], false],
        ["address gone", candidate, [{ ...client, address: "0x1" }], false],
        ["other class", candidate, [{ ...client, class: "org.example.App" }], false],
        ["main window title", candidate, [{ ...client, title: "All Items - 1Password" }], false],
        ["client list unavailable", candidate, null, false]
    ];
    for (const [name, c, clients, expected] of cases)
        assert.equal(P.confirmCandidate(c, clients).confirmed, expected, name);
});

test("a confirmed window becomes an episode only with a requester, named only when there is one", () => {
    assert.deepEqual(P.requesterOutcome({ candidates: [] }), { episode: false, count: 0, pid: null });
    assert.deepEqual(P.requesterOutcome(null), { episode: false, count: 0, pid: null });
    assert.deepEqual(P.requesterOutcome({ candidates: [{ pid: 42, source: "ssh-agent" }] }), { episode: true, count: 1, pid: 42 });
    assert.deepEqual(P.requesterOutcome({ candidates: [{ pid: 42 }, { pid: 43 }] }), { episode: true, count: 2, pid: null });
});

test("an episode expires only after expired_min_seconds, and reconciled episodes never do", () => {
    const c = config();
    assert.equal(P.classifyEnd({ openedAtMs: OPEN }, OPEN + 59_800, c), "expired");
    assert.equal(P.classifyEnd({ openedAtMs: OPEN }, OPEN + 59_000, c), "expired");
    assert.equal(P.classifyEnd({ openedAtMs: OPEN }, OPEN + 58_999, c), "answered");
    assert.equal(P.classifyEnd({ openedAtMs: OPEN }, OPEN + 2_500, c), "answered");
    assert.equal(P.classifyEnd({ openedAtMs: OPEN, reconciled: true }, OPEN + 600_000, c), "reconciled");
    assert.equal(P.classifyEnd({ openedAtMs: OPEN }, OPEN + 59_800, config({ watcher: { expired_min_seconds: 90 } })), "answered");
});

test("the grace period starts only for an expired, fresh episode while Rod is not present", () => {
    const ep = { reconciled: false };
    const c = config();
    const cases = [
        ["away at expiry", ep, "expired", "away", c, true],
        ["locked at expiry", ep, "expired", "locked", c, true],
        ["unknown at expiry", ep, "expired", "unknown", c, true],
        ["present at expiry", ep, "expired", "present", c, false],
        ["answered", ep, "answered", "away", c, false],
        ["reconciled", { reconciled: true }, "expired", "away", c, false],
        ["fallback disabled", ep, "expired", "away", config({ watcher: { fallback: false } }), false],
        ["state excluded", ep, "expired", "unknown", config({ alerts: { presence_states: ["idle", "away", "locked"] } }), false],
        ["already attempted", { reconciled: false, fallbackAttempted: true }, "expired", "away", c, false]
    ];
    for (const [name, episode, classification, state, cfg, expected] of cases)
        assert.equal(P.graceEligible(episode, classification, state, cfg).eligible, expected, name);
});

test("when the grace period ends, any return since the expiry cancels the fallback", () => {
    const ep = { reconciled: false, openedAtMs: OPEN, closedAtMs: CLOSED, expiredAt: EXPIRED_AT };
    const c = config();
    const cases = [
        ["away throughout", ep, "away", EXPIRED_AT - 300, c, true],
        ["expired_min_seconds raised past the lifetime since expiry", ep, "away", null, config({ watcher: { expired_min_seconds: 90 } }), false],
        ["never seen present", ep, "idle", null, c, true],
        ["present at fire time", ep, "present", EXPIRED_AT + 100, c, false],
        ["came back and left again", ep, "idle", EXPIRED_AT + 30, c, false],
        ["present in the second of the expiry", ep, "away", EXPIRED_AT, c, false],
        ["reconciled", { ...ep, reconciled: true }, "away", null, c, false],
        ["fallback disabled since expiry", ep, "away", null, config({ watcher: { fallback: false } }), false],
        ["state excluded at fire time", ep, "locked", null, config({ alerts: { presence_states: ["idle", "away"] } }), false],
        ["already attempted", { ...ep, fallbackAttempted: true }, "away", null, c, false]
    ];
    for (const [name, episode, state, lastPresentAt, cfg, expected] of cases)
        assert.equal(P.fallbackDecision(episode, state, lastPresentAt, cfg).send, expected, name);
});

test("presence is unknown until observations are valid, locked wins, and a fresh monitor cannot claim present", () => {
    const c = config();
    const now = OPEN + 30_000;
    const valid = { ...P.activityReset(OPEN, null), valid: true };
    const known = { ...valid, inputKnown: true, lastInputMs: now - 10_000 };
    const base = { hyprlandUp: true, lock: "unlocked", activity: known, nowMs: now };
    const cases = [
        ["input 10 s ago", base, "present"],
        ["input 60 s ago", { ...base, activity: { ...known, lastInputMs: now - 60_000 } }, "idle"],
        ["input 300 s ago", { ...base, activity: { ...known, lastInputMs: now - 300_000 } }, "away"],
        ["locked while away", { ...base, lock: "locked", activity: { ...known, lastInputMs: now - 300_000 } }, "locked"],
        ["lock undetermined", { ...base, lock: "unknown" }, "unknown"],
        ["Hyprland down", { ...base, hyprlandUp: false, lock: "locked" }, "unknown"],
        ["5 s monitor not yet idle", { ...base, activity: P.activityReset(OPEN, null) }, "unknown"],
        ["no input seen since the monitor was created", { ...base, activity: valid }, "unknown"],
        ["no input seen, but created long enough ago", { ...base, activity: valid, nowMs: OPEN + 61_000 }, "idle"]
    ];
    for (const [name, obs, expected] of cases)
        assert.equal(P.derivePresence(obs, c), expected, name);
});

// Replays monitor and close events the way shell.qml applies them, with the
// watcher's 1 s ticks in between (none across a ["suspend"] marker), and
// returns the published presence after each listed event plus
// last_present_at.
function replay(events, cfg = config()) {
    let activity = P.activityReset(OPEN, null);
    let presence = "unknown";
    let lastPresentAt = null;
    let lastMs = OPEN;
    let suspended = false;
    const states = [];
    const notes = [];
    const apply = (type, atMs) => {
        const r = P.activityReduce(activity, { type, atMs });
        activity = r.state;
        if (r.note) notes.push(r.note);
        const next = P.derivePresence({ hyprlandUp: true, lock: "unlocked", activity, nowMs: atMs }, cfg);
        lastPresentAt = P.nextLastPresentAt(presence, next, lastPresentAt, Math.floor(atMs / 1000));
        presence = next;
        lastMs = atMs;
    };
    for (const [type, atMs] of events) {
        if (type === "suspend") {
            suspended = true;
            continue;
        }
        if (!suspended)
            for (let t = lastMs + 1000; t < atMs; t += 1000)
                apply("tick", t);
        suspended = false;
        apply(type, atMs);
        states.push(presence);
    }
    return { presence, lastPresentAt, states, notes, activity };
}

// Valid at +5 s, Rod uses the PC from +6 s to +15 s, then leaves; idle from
// +75 s (60 s after his last input).
const LEFT = [
    ["idle", OPEN + 5_000], ["active", OPEN + 6_000], ["tick", OPEN + 6_320],
    ["idle", OPEN + 20_000], ["tick", OPEN + 74_000], ["tick", OPEN + 75_000]
];

test("Rod's input and departure move presence from present to idle", () => {
    const r = replay(LEFT);
    assert.deepEqual(r.states.slice(2), ["present", "present", "present", "idle"]);
    assert.equal(r.lastPresentAt, Math.floor((OPEN + 75_000) / 1000));
});

test("activity right after a window closes is discarded when the monitor goes idle again", () => {
    const left = replay(LEFT);
    const X = OPEN + 90_000;
    for (const order of [
        [["close", X], ["active", X + 11]],
        [["active", X], ["close", X + 100]]
    ]) {
        const r = replay([...LEFT, ...order, ["tick", X + 400], ["tick", X + 3_000], ["idle", X + 5_011], ["tick", X + 6_000]]);
        assert.ok(r.states.slice(LEFT.length).every(s => s === "idle"), "never present: " + r.states.join(","));
        assert.equal(r.lastPresentAt, left.lastPresentAt);
        assert.deepEqual(r.notes, ["suspect", "discarded"]);
    }
});

test("activity right after a window closes counts once input continues past the confirmation time", () => {
    const X = OPEN + 90_000;
    const r = replay([...LEFT, ["close", X], ["active", X + 11], ["tick", X + 400], ["tick", X + 5_520]]);
    assert.deepEqual(r.states.slice(LEFT.length), ["idle", "idle", "idle", "present"]);
    assert.ok(r.lastPresentAt >= Math.floor((X + 11) / 1000));
    assert.deepEqual(r.notes, ["suspect", "confirmed"]);
});

test("activity away from any close counts once the close window has passed", () => {
    const X = OPEN + 90_000;
    const r = replay([...LEFT, ["close", X - 2_000], ["active", X], ["tick", X + 320]]);
    assert.deepEqual(r.states.slice(LEFT.length), ["idle", "idle", "present"]);
    assert.equal(r.lastPresentAt, Math.floor((X + 320) / 1000));
    assert.deepEqual(r.notes, []);
});

test("the first idle report after start counts idleness from 5 s before it, not from the start", () => {
    // Rod types for 60 s after the start, then pauses.
    const r = replay([["idle", OPEN + 65_000], ["tick", OPEN + 66_000], ["tick", OPEN + 125_000]]);
    assert.deepEqual(r.states, ["unknown", "unknown", "idle"]);
});

test("activity held before a suspend is dropped, not confirmed by a timer after the resume", () => {
    const left = replay(LEFT);
    const X = OPEN + 90_000;
    const r = replay([...LEFT, ["close", X], ["active", X + 11], ["suspend"], ["tick", X + 600_000], ["tick", X + 601_000]]);
    assert.deepEqual(r.states.slice(LEFT.length), ["idle", "idle", "unknown", "unknown"]);
    assert.deepEqual(r.notes, ["suspect", "resume"]);
    assert.equal(r.lastPresentAt, left.lastPresentAt);
});

test("the feed carries activity_pending_until only while activity is held", () => {
    const X = OPEN + 90_000;
    const held = replay([...LEFT, ["close", X], ["active", X + 11]]).activity;
    const until = P.activityPendingUntil(held);
    assert.equal(until, X + 11 + P.CONFIRM_MS);
    assert.equal(P.presenceDocument("desk", "idle", X + 20, 1, until).activity_pending_until, Math.ceil(until / 1000));
    const resolved = replay([...LEFT, ["close", X], ["active", X + 11], ["idle", X + 5_011]]).activity;
    assert.equal(P.activityPendingUntil(resolved), null);
    assert.equal("activity_pending_until" in P.presenceDocument("desk", "idle", X, 1, null), false);
});

test("a discarded blip keeps idle and away measured from the last real input", () => {
    const X = OPEN + 250_000;
    const r = replay([...LEFT, ["close", X], ["active", X + 11], ["idle", X + 5_011],
        ["tick", OPEN + 314_000], ["tick", OPEN + 315_000]]);
    assert.deepEqual(r.states.slice(LEFT.length), ["idle", "idle", "idle", "idle", "away"]);
});

test("last_present_at follows present, stops when Rod leaves and survives a restart", () => {
    assert.equal(P.nextLastPresentAt("unknown", "present", null, 100), 100);
    assert.equal(P.nextLastPresentAt("present", "idle", 90, 100), 100);
    assert.equal(P.nextLastPresentAt("idle", "away", 90, 100), 90);
    assert.equal(P.restoredLastPresentAt({ last_present_at: 90 }, 100), 90);
    assert.equal(P.restoredLastPresentAt({ last_present_at: 200 }, 100), null);
    assert.equal(P.restoredLastPresentAt({ last_present_at: "90" }, 100), null);
    assert.equal(P.restoredLastPresentAt(null, 100), null);
});

test("invalid config values fall back to their defaults with a warning, missing ones silently", () => {
    const silent = P.normaliseConfig({ watcher: { fallback_grace_seconds: 30 } });
    assert.deepEqual(silent.warnings, []);
    assert.equal(silent.config.watcher.fallback_grace_seconds, 30);
    assert.equal(silent.config.watcher.expired_min_seconds, 59);

    const invalid = P.normaliseConfig({
        presence: { present_seconds: 0 },
        watcher: { fallback: "yes", confirm_seconds: 0.5 },
        alerts: { presence_states: ["away", "asleep"] }
    });
    assert.equal(invalid.warnings.length, 3);
    assert.equal(invalid.config.presence.present_seconds, 60);
    assert.equal(invalid.config.watcher.fallback, true);
    assert.equal(invalid.config.watcher.confirm_seconds, 0.5);
    assert.deepEqual(invalid.config.alerts.presence_states, ["idle", "away", "locked", "unknown"]);

    const inverted = P.normaliseConfig({ presence: { present_seconds: 600 } });
    assert.equal(inverted.warnings.length, 1);
    assert.deepEqual(inverted.config.presence, { present_seconds: 60, away_seconds: 300 });

    assert.equal(P.normaliseConfig(undefined, true).warnings.length, 1);
    assert.equal(P.normaliseConfig([1]).warnings.length, 1);
});

test("the feed the watcher writes is read as fresh by the shared library", (t) => {
    try {
        execFileSync("jq", ["--version"], { stdio: "ignore" });
    } catch {
        t.skip("jq is not installed");
        return;
    }
    const runtime = fs.mkdtempSync(path.join(os.tmpdir(), "opa-watcher-test-"));
    try {
        fs.mkdirSync(path.join(runtime, "op-approval"), { mode: 0o700 });
        const now = Date.now();
        const doc = P.presenceDocument("desk", "away", now, Math.floor(now / 1000) - 400);
        fs.writeFileSync(path.join(runtime, "op-approval", "presence.json"), JSON.stringify(doc) + "\n", { mode: 0o600 });
        const out = execFileSync(path.join(LIB, "claim"), ["status"], {
            env: { PATH: process.env.PATH, HOME: runtime, XDG_RUNTIME_DIR: runtime, XDG_CONFIG_HOME: path.join(runtime, "config") },
            encoding: "utf8"
        });
        const presence = JSON.parse(out).presence;
        assert.equal(presence.fresh, true);
        assert.equal(presence.state, "away");
        assert.equal(presence.last_present_at, doc.last_present_at);
        assert.match(doc.updated_at, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$/);
    } finally {
        fs.rmSync(runtime, { recursive: true, force: true });
    }
});
