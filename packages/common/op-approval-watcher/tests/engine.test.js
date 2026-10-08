// Engine scenarios: each discovery case and acceptance scenario replayed
// through Engine.js against a simulated host with a virtual clock. They run
// against the shared engine alone, so one test covers every platform.
// Run from the repository root:
//   node --test packages/common/op-approval-watcher/tests/
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const P = require("../.local/share/op-approval-watcher/Policy.js");
const { createEngine } = require("../.local/share/op-approval-watcher/Engine.js");

const E = createEngine(P);
const T0 = 1_791_000_000_000;
const CODE = { policy: "policy v1", engine: "engine v1" };

// 1Password log lines as discovery recorded them, without the leading
// level and timestamp, which Host.line adds.
const LINES = {
    sshTimeout: "runtime-worker(ThreadId(9)) [1P:ssh/op-ssh-agent/src/lib.rs:405] ssh authorization prompt timed out",
    sshNotAuthorised: "runtime-worker(ThreadId(8)) [1P:ssh/op-ssh-agent/src/lib.rs:649] Session was not authorized",
    sshPromptError: "runtime-worker(ThreadId(8)) [1P:app/op-app/src/app/components/ssh_agent.rs:206] received error from SSH auth prompt",
    displaySleep: "runtime-worker(ThreadId(9)) [1P:app/op-app/src/app/backend/lock.rs:293] Locked. Reason: Automatic(DeviceWentToSleep).",
    unlock: "runtime-worker(ThreadId(3)) [1P:data/op-unlock/src/lib.rs:213] System unlock proceeding with DeviceEnclave backend.",
    appCancel: "runtime-worker(ThreadId(2903)) [1P:foundation/op-system-auth/src/apple.rs:433] AppCancel invoked by a timed-out prompt due to serialized queue delay",
    biometry: "runtime-worker(ThreadId(9)) [1P:op-automated-unlock/src/lib.rs:370] Failed to authorize using system biometry: UnlockInitError(SystemAuthError(FailedSystemAuthenticationChallenge))",
    envDenied: "runtime-worker(ThreadId(12)) [1P:app/op-app/src/app/backend/developer/environment/mod.rs:233] Developer Environment file mount auth was denied by the user"
};

const SSH = { candidates: [{ pid: 4242, comm: "ssh", source: "ssh-agent" }] };
const OP = { candidates: [{ pid: 4343, comm: "op", source: "op" }] };
const NONE = { candidates: [] };
const IDENTITY = { machine: "mac", harness: "codex", project: "proxmox", location: "Ghostty, herdr proxmox/agents" };

// A host that answers every effect the way a platform host would, with a
// 5 s input monitor driven by simulated input, and records what it did.
class Host {
    constructor(opts = {}) {
        this.now = T0;
        this.state = E.initial();
        this.timers = new Map();
        this.lock = opts.lock || "unlocked";
        this.config = opts.config === undefined ? null : JSON.stringify(opts.config);
        this.code = { ...CODE };
        this.requesters = opts.requesters || SSH;
        this.identity = opts.identity || IDENTITY;
        this.claimCode = opts.claimCode === undefined ? 0 : opts.claimCode;
        this.openAtStart = opts.openAtStart || [];
        this.rejected = new Set();
        this.slowConfirm = new Map();  // key -> ms the confirmation check takes
        this.answers = [];             // [dueMs, fn] for slow checks
        this.runs = [];
        this.logs = [];
        this.feeds = [];
        this.exits = [];
        this.lastInput = -Infinity;
        this.monitorIdle = false;
        this.monitorFrom = T0;
    }

    send(event) {
        const r = E.step(this.state, { atMs: this.now, ...event });
        this.state = r.state;
        for (const fx of r.effects) this.apply(fx);
    }

    apply(fx) {
        switch (fx.type) {
        case "log": this.logs.push(fx.message); break;
        case "write_feed": this.feeds.push(fx.document); break;
        case "exit": this.exits.push(fx.code); break;
        case "reset_input": this.monitorIdle = false; this.monitorFrom = this.now; break;
        case "set_timer": this.timers.set(fx.id, this.now + fx.delayMs); break;
        case "cancel_timer": this.timers.delete(fx.id); break;
        case "observe": {
            const answer = () => this.send({ type: "observed", id: fx.id, result: this.observe(fx) });
            const delay = fx.what === "candidate" ? this.slowConfirm.get(fx.key) : undefined;
            if (delay) this.answers.push([this.now + delay, answer]);
            else this.later(answer);
            break;
        }
        case "run": this.runs.push(fx); this.later(() => this.send({ type: "helper_done", id: fx.id, ...this.helper(fx) })); break;
        default: throw new Error("unexpected effect " + fx.type);
        }
    }

    later(fn) {
        (this.queue = this.queue || []).push(fn);
    }

    drain() {
        while (this.queue && this.queue.length) this.queue.shift()();
    }

    observe(fx) {
        switch (fx.what) {
        case "lock": return { state: this.lock };
        case "session": return { state: "up" };
        case "config": return { text: this.config };
        case "code": return { ...this.code };
        case "open_candidates": return { candidates: this.openAtStart };
        case "candidate": return this.rejected.has(fx.key) ? { confirmed: false, reason: "width differs" } : { confirmed: true, reason: "approval window" };
        default: throw new Error("unexpected observation " + fx.what);
        }
    }

    helper(fx) {
        if (fx.helper === "requesters") return { code: 0, output: JSON.stringify(this.requesters) };
        if (fx.helper === "locate") return { code: 0, output: JSON.stringify(this.identity) };
        if (fx.helper === "claim") return { code: this.claimCode, output: this.claimCode === 0 ? "granted\n" : "already alerted during this absence\n" };
        if (fx.helper === "publish") return { code: 0, output: '{"result":"sent","http_status":200}' };
        throw new Error("unexpected helper " + fx.helper);
    }

    start() {
        this.send({ type: "start", previousFeed: null, config: this.config, hostname: "mac", runId: "test", code: CODE });
        this.drain();
        return this;
    }

    // Moves the clock to `ms` after T0: ticks every second, timers on time,
    // and the 5 s monitor reporting idle once input stops.
    until(ms) {
        const end = T0 + ms;
        for (;;) {
            const nextTick = Math.floor(this.now / 1000) * 1000 + 1000;
            const nextTimer = Math.min(Infinity, ...this.timers.values());
            const idleAt = this.monitorIdle ? Infinity : Math.max(this.lastInput, this.monitorFrom) + 5000;
            const nextAnswer = Math.min(Infinity, ...this.answers.map(a => a[0]));
            const next = Math.min(nextTick, nextTimer, idleAt, nextAnswer);
            if (next > end) break;
            // Overdue timers (after a suspend) fire at the current time.
            this.now = Math.max(this.now, next);
            if (next === nextAnswer) {
                const i = this.answers.findIndex(a => a[0] === next);
                this.answers.splice(i, 1)[0][1]();
            } else if (next === idleAt) {
                this.monitorIdle = true;
                this.send({ type: "input", state: "idle" });
            } else if (next === nextTimer) {
                const id = [...this.timers].find(([, t]) => t === next)[0];
                this.timers.delete(id);
                this.send({ type: "timer_fired", id });
            } else {
                this.send({ type: "tick" });
            }
            this.drain();
        }
        this.now = end;
        return this;
    }

    at(ms, event) {
        this.until(ms);
        this.send(event);
        this.drain();
        return this;
    }

    input(ms) {
        this.until(ms);
        this.lastInput = this.now;
        if (this.monitorIdle) {
            this.monitorIdle = false;
            this.send({ type: "input", state: "active" });
            this.drain();
        }
        return this;
    }

    open(ms, key, extra = {}) {
        return this.at(ms, { type: "candidate_open", key, openedAtMs: T0 + ms, reconciled: false, source: "approval", ...extra });
    }

    close(ms, key) {
        return this.at(ms, { type: "candidate_closed", key, closedAtMs: T0 + ms });
    }

    // A line written at writtenMs (default: when it arrives at ms).
    line(ms, text, writtenMs = ms) {
        const stamp = new Date(T0 + writtenMs).toISOString().replace("Z", "+00:00");
        return this.at(ms, { type: "log_line", line: "INFO  " + stamp + " " + text });
    }

    // The machine sleeps for ms: the clock moves with no ticks or timers.
    suspend(ms) {
        this.now += ms;
        return this;
    }

    helpers(name) {
        return this.runs.filter(r => r.helper === name);
    }

    fallbacks() {
        return this.helpers("publish");
    }
}

// Rod used the Mac until AWAY_FROM; presence is away from AWAY_FROM + 300 s.
const AWAY_FROM = 10_000;
const PROMPT = 400_000;
const GRACE = 120_000;

function awayHost(opts) {
    const h = new Host(opts).start();
    for (let t = 6_000; t <= AWAY_FROM; t += 1_000) h.input(t);
    return h.until(PROMPT - 1_000);
}

function assertOneFallback(h, category, identity) {
    assert.equal(h.helpers("claim").length, 1, "one claim");
    const claim = h.helpers("claim")[0].args;
    assert.deepEqual(claim.slice(0, 3), ["take", "--source", "watcher"]);
    assert.ok(claim.includes("--require-away"));
    const publish = h.fallbacks();
    assert.equal(publish.length, 1, "one fallback");
    const args = publish[0].args;
    assert.equal(args[args.indexOf("--category") + 1], category);
    assert.deepEqual(JSON.parse(args[args.indexOf("--identity") + 1]), identity);
}

test("case 2: an SSH prompt left alone while Rod is away sends one fallback after the grace period", () => {
    const h = awayHost();
    h.open(PROMPT, "w1").line(PROMPT + 60_000, LINES.sshTimeout).close(PROMPT + 60_000, "w1");
    h.until(PROMPT + 60_000 + GRACE);
    assert.equal(h.fallbacks().length, 0, "nothing before the grace period ends");
    h.until(PROMPT + 60_000 + GRACE + 2_000);
    assertOneFallback(h, "ssh", { ...IDENTITY, process: "ssh" });
    assert.deepEqual(h.helpers("requesters")[0].args, ["--opened-at", ((T0 + PROMPT) / 1000).toFixed(3)]);
    assert.deepEqual(h.helpers("locate")[0].args, ["--pid", "4242"]);
});

test("case 13: an SSH prompt cancelled after 18.5 s when the locked screen's display turns off is not given", () => {
    const h = awayHost({ lock: "locked" });
    const close = PROMPT + 18_500;
    h.open(PROMPT, "w1").line(close - 30, LINES.displaySleep).line(close - 20, LINES.sshPromptError)
        .line(close - 10, LINES.sshNotAuthorised).close(close, "w1").until(close + GRACE + 2_000);
    assertOneFallback(h, "ssh", { ...IDENTITY, process: "ssh" });
    assert.ok(h.logs.some(l => /ended: not given \(1Password logged a cancellation\)/.test(l)), h.logs.join("\n"));
});

test("case 3: an op prompt that expires with no log line is not given by its lifetime", () => {
    const h = awayHost({ requesters: OP });
    h.open(PROMPT, "w1").close(PROMPT + 60_300, "w1").until(PROMPT + 60_300 + GRACE + 2_000);
    assertOneFallback(h, "op-cli", { ...IDENTITY, process: "op" });
});

test("an unattended prompt cancelled early with no log line is not given, because no input came", () => {
    const h = awayHost();
    h.open(PROMPT, "w1").close(PROMPT + 20_000, "w1").until(PROMPT + 20_000 + GRACE + 2_000);
    assertOneFallback(h, "ssh", { ...IDENTITY, process: "ssh" });
    assert.ok(h.logs.some(l => /not given \(no input while open\)/.test(l)));
});

test("case 15: a browser extension unlock that times out after 30 s is reported as an unlock", () => {
    const h = awayHost({ requesters: NONE });
    h.line(PROMPT - 40, LINES.unlock).open(PROMPT, "ca1", { source: "system-auth" })
        .line(PROMPT + 30_000, LINES.appCancel).line(PROMPT + 30_005, LINES.biometry)
        .close(PROMPT + 30_270, "ca1").until(PROMPT + 30_270 + GRACE + 2_000);
    assertOneFallback(h, "unlock", {});
});

test("a system Touch ID dialog with no 1Password unlock request is not an approval", () => {
    const h = awayHost({ requesters: NONE });
    h.open(PROMPT, "ca1", { source: "system-auth" }).close(PROMPT + 30_000, "ca1").until(PROMPT + 30_000 + GRACE + 2_000);
    assert.equal(h.helpers("requesters").length, 0);
    assert.equal(h.helpers("claim").length, 0);
    assert.ok(h.logs.some(l => /not an approval: no 1Password unlock request/.test(l)));
});

test("case 17: an Environments read whose requester already exited is reported as an Environment, naming the machine only", () => {
    const h = awayHost({ requesters: NONE, lock: "locked" });
    // Discovery: both lines are written up to 0.4 s before the window is seen closing.
    h.line(PROMPT - 40, LINES.unlock).open(PROMPT, "w1").line(PROMPT + 59_900, LINES.appCancel)
        .line(PROMPT + 59_990, LINES.envDenied).close(PROMPT + 60_100, "w1").until(PROMPT + 60_100 + GRACE + 2_000);
    assertOneFallback(h, "environment", {});
});

test("overlapping approvals are one episode with one fallback, named after the most specific type", () => {
    const h = awayHost();
    h.line(PROMPT - 40, LINES.unlock).open(PROMPT, "ca1", { source: "system-auth" }).open(PROMPT + 500, "w1")
        .close(PROMPT + 30_000, "ca1").line(PROMPT + 60_500, LINES.sshTimeout).close(PROMPT + 60_500, "w1")
        .until(PROMPT + 60_500 + GRACE + 2_000);
    assertOneFallback(h, "ssh", {});
    assert.ok(h.logs.some(l => /overlapping episode .*: merged/.test(l)));
});

test("cases 4 and 5: a prompt Rod rejects at the Mac sends nothing, even with a not-authorised line", () => {
    const h = new Host().start();
    for (let t = 6_000; t <= 20_000; t += 1_000) h.input(t);
    h.open(20_500, "w1").input(23_000).line(24_000, LINES.sshNotAuthorised).close(24_000, "w1").until(24_000 + GRACE + 10_000);
    assert.equal(h.helpers("claim").length, 0);
    assert.ok(h.logs.some(l => /no fallback \(present when it closed\)/.test(l)));
});

test("case 9: a prompt Rod approves and then leaves untouched for 10 s sends nothing", () => {
    const h = new Host().start();
    h.input(6_000).until(20_000);
    h.open(20_000, "w1").input(22_490).close(22_500, "w1").until(22_500 + 10_000 + GRACE + 300_000);
    assert.equal(h.helpers("claim").length, 0);
    assert.ok(h.logs.some(l => /ended: answered \(input while open\)/.test(l)), h.logs.join("\n"));
});

test("a prompt approved within 5 s of the watcher starting sends nothing, though Rod then leaves", () => {
    const h = new Host().start();
    h.open(1_000, "w1").input(3_000).close(3_100, "w1").until(3_100 + GRACE + 600_000);
    assert.equal(h.helpers("claim").length, 0);
    assert.ok(h.logs.some(l => /ended: answered \(input not observed throughout\)/.test(l)), h.logs.join("\n"));
});

test("a window that opens before another closes is merged even when it is confirmed after that close", () => {
    const h = awayHost();
    h.open(PROMPT, "w1").open(PROMPT + 59_500, "w2").close(PROMPT + 60_000, "w1")
        .close(PROMPT + 80_000, "w2").until(PROMPT + 80_000 + GRACE + 2_000);
    assert.equal(h.helpers("claim").length, 1);
    assert.ok(h.logs.some(l => /overlapping episode .*: merged/.test(l)), h.logs.join("\n"));
});

test("a late confirmation that overlaps two groups merges them into one", () => {
    const h = awayHost();
    // A closes while B awaits confirmation; C opens after A closed and is
    // confirmed before B.
    h.slowConfirm.set("B", 3_000);
    h.open(PROMPT, "A").open(PROMPT + 59_800, "B").close(PROMPT + 60_000, "A").open(PROMPT + 60_100, "C")
        .until(PROMPT + 62_000);
    assert.equal(Object.keys(h.state.groups).length, 2, "A and C are separate before B is confirmed");
    h.close(PROMPT + 70_000, "B").close(PROMPT + 80_000, "C").until(PROMPT + 80_000 + GRACE + 2_000);
    assert.equal(h.helpers("claim").length, 1, h.logs.join("\n"));
});

test("a cancellation written after a prompt closed does not count against it", () => {
    const h = new Host().start();
    h.open(1_000, "w1").input(3_000).close(3_100, "w1").line(4_100, LINES.sshNotAuthorised)
        .until(3_100 + GRACE + 600_000);
    assert.equal(h.helpers("claim").length, 0);
});

test("a cancellation written before the close but read after it still counts", () => {
    const h = new Host().start();
    h.open(1_000, "w1").input(3_000).close(3_100, "w1").line(3_300, LINES.sshNotAuthorised, 3_000);
    for (let t = 30_000; t <= 400_000; t += 50_000) h.until(t);
    h.until(400_000);
    assert.ok(h.logs.some(l => /not given \(1Password logged a cancellation\)/.test(l)), h.logs.join("\n"));
});

test("a 1Password unlock request written after the Touch ID dialog opened does not qualify it", () => {
    const h = awayHost({ requesters: NONE });
    h.open(PROMPT, "ca1", { source: "system-auth" }).line(PROMPT + 800, LINES.unlock)
        .close(PROMPT + 30_000, "ca1").until(PROMPT + 30_000 + GRACE + 2_000);
    assert.equal(h.helpers("claim").length, 0);
    assert.ok(h.logs.some(l => /not an approval: no 1Password unlock request/.test(l)));
});

test("a grace period that ends during a suspend is cancelled on resume, before the fallback can fire", () => {
    const h = awayHost();
    h.open(PROMPT, "w1").close(PROMPT + 60_000, "w1").until(PROMPT + 100_000)
        .suspend(300_000).until(PROMPT + 400_500);
    assert.equal(h.helpers("claim").length, 0);
    assert.ok(h.logs.some(l => /fallback cancelled \(resume\)/.test(l)), h.logs.join("\n"));
});

test("Rod returning during the grace period cancels the fallback, even if he leaves again", () => {
    const h = awayHost();
    h.open(PROMPT, "w1").close(PROMPT + 60_000, "w1").input(PROMPT + 100_000).until(PROMPT + 60_000 + GRACE + 2_000);
    assert.equal(h.helpers("claim").length, 0);
    assert.ok(h.logs.some(l => /no fallback \(present\)|no fallback \(present since it closed\)/.test(l)), h.logs.join("\n"));
});

test("a refused claim publishes nothing", () => {
    const h = awayHost({ claimCode: 3 });
    h.open(PROMPT, "w1").close(PROMPT + 60_000, "w1").until(PROMPT + 60_000 + GRACE + 2_000);
    assert.equal(h.helpers("claim").length, 1);
    assert.equal(h.fallbacks().length, 0);
});

test("an approval window already open at start is never fallback-eligible", () => {
    const h = new Host({ openAtStart: [{ key: "w0", source: "approval" }] }).start();
    h.until(400_000).close(400_000, "w0").until(400_000 + GRACE + 2_000);
    assert.deepEqual(h.helpers("requesters")[0].args, ["--reconciled"]);
    assert.equal(h.helpers("claim").length, 0);
});

test("a window the platform rejects never becomes an episode", () => {
    const h = awayHost();
    h.rejected.add("qa");
    h.open(PROMPT, "qa").close(PROMPT + 60_000, "qa").until(PROMPT + 60_000 + GRACE + 2_000);
    assert.equal(h.helpers("requesters").length, 0);
    assert.equal(h.helpers("claim").length, 0);
});

test("sleep during the grace period cancels the fallback", () => {
    const h = awayHost();
    h.open(PROMPT, "w1").close(PROMPT + 60_000, "w1").at(PROMPT + 90_000, { type: "sleep" });
    h.until(PROMPT + 60_000 + GRACE + 2_000);
    assert.equal(h.helpers("claim").length, 0);
});

test("a config change during the grace period applies when it fires", () => {
    const h = awayHost();
    h.open(PROMPT, "w1").line(PROMPT + 60_000, LINES.sshTimeout).close(PROMPT + 60_000, "w1");
    h.config = JSON.stringify({ watcher: { fallback: false } });
    h.until(PROMPT + 60_000 + GRACE + 2_000);
    assert.equal(h.helpers("claim").length, 0);
    assert.ok(h.logs.some(l => /no fallback \(fallback disabled\)/.test(l)));
});

test("new shared code makes the watcher exit so the service manager restarts it", () => {
    const h = awayHost();
    h.open(PROMPT, "w1").close(PROMPT + 60_000, "w1");
    assert.deepEqual(h.exits, []);
    h.code = { policy: "policy v2", engine: "engine v1" };
    h.until(PROMPT + 75_000);
    assert.deepEqual(h.exits, [75]);
    assert.ok(h.logs.some(l => /fallback cancelled \(restart for new code\)/.test(l)));
});

test("the feed carries the engine hash, which differs when either shared file changes", () => {
    const h = new Host().start();
    const hash = h.feeds[0].engine;
    assert.match(hash, /^[0-9a-f]{8}$/);
    assert.equal(hash, P.contentHash(CODE.policy + "\n" + CODE.engine));
    assert.notEqual(hash, P.contentHash("policy v1\nengine v2"));
});

test("a lost session writes unknown presence and exits", () => {
    const h = awayHost();
    h.send({ type: "session", state: "lost", detail: "hyprctl version exit 1" });
    assert.deepEqual(h.exits, [1]);
    assert.equal(h.feeds[h.feeds.length - 1].state, "unknown");
});

test("presence follows Rod: present, then idle and away on the wall clock, locked while locked", () => {
    const h = new Host().start();
    h.until(5_500);
    assert.equal(h.state.presence, "unknown", "invalid until 5 s of idleness");
    h.input(6_000).until(7_000);
    assert.equal(h.state.presence, "present");
    h.until(6_000 + 61_000);
    assert.equal(h.state.presence, "idle");
    h.until(6_000 + 301_000);
    assert.equal(h.state.presence, "away");
    h.lock = "locked";
    h.until(6_000 + 312_000);
    assert.equal(h.state.presence, "locked");
    assert.equal(h.feeds[h.feeds.length - 1].state, "locked");
});

test("waking from sleep invalidates input until the monitor reports idle again", () => {
    const h = awayHost();
    h.at(PROMPT, { type: "wake" });
    assert.equal(h.state.presence, "unknown");
    h.open(PROMPT + 1_000, "w1").close(PROMPT + 20_000, "w1").until(PROMPT + 20_000 + GRACE + 2_000);
    assert.equal(h.helpers("claim").length, 0, "rule 3 needs observations throughout");
});
