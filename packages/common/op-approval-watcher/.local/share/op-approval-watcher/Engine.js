// Orchestration of the 1Password approval watcher, shared by every platform.
//
// A pure reducer: createEngine(POLICY).step(state, event) returns
// {state, effects}. No I/O, no clock and no timers: every event carries its
// own atMs, and the platform host carries out the effects and reports their
// results back as events. The host only observes its desktop and translates
// what it sees; every decision, threshold and schedule lives here or in
// Policy.js. Written in the same JavaScript subset as Policy.js.
//
// Events (all with atMs):
//   start {previousFeed, config, hostname, runId, code: {policy, engine}}
//   config {text}                 config.json text, null when missing
//   tick                          every second
//   input {state: idle|active}    5 s input monitor; macOS stamps active
//                                 with the real input time
//   surface_closed                any window or layer closed (Omarchy)
//   lock {state}                  locked, unlocked or unknown
//   session {state}               up, inactive (not on the console) or lost
//   sleep, wake
//   log_line {line}               new line of 1Password's log
//   candidate_open {key, openedAtMs, reconciled, source, kind}
//   candidate_closed {key, closedAtMs}
//   helper_done {id, code, output}
//   observed {id, result}
//   timer_fired {id}
//
// Effects:
//   write_feed {document}
//   run {id, helper, args, deadlineMs}   helper: requesters, locate, claim, publish
//   observe {id, what, key}              what: candidate, open_candidates, lock,
//                                        session, config, code
//   reset_input                          discard the input monitor, start a new one
//   set_timer {id, delayMs}, cancel_timer {id}
//   log {level: info|warn, message}
//   exit {code}

// eslint-disable-next-line no-unused-vars
function createEngine(P) {
    var LOCK_POLL_MS = 10000;
    var LOCK_POLL_PENDING_MS = 2000;
    var SESSION_POLL_MS = 10000;
    var CONFIG_POLL_MS = 30000;
    var CODE_POLL_MS = 10000;
    var FEED_REFRESH_MS = 10000;
    // An observation the host never answered is given up after this long.
    var OBSERVE_STALE_MS = 30000;
    // A group is classified this long after its last window closed, so log
    // lines written before the close but read after it still count, and a
    // window that opened before the close can still be confirmed and merged.
    var CLOSE_SETTLE_MS = 1500;
    // A log line without its own timestamp is placed by its arrival, which
    // lags the write by up to a few hundred milliseconds.
    var ARRIVAL_SLACK_MS = 500;
    // Raw input, validity gaps and log signals are kept this long; an episode
    // older than that is decided by its lifetime alone.
    var HISTORY_MS = 600000;
    var DEADLINES = { requesters: 10000, locate: 15000, claim: 15000, publish: 20000 };
    // Exit code for a restart on new code; any non-zero code makes systemd
    // (Restart=on-failure) and launchd (KeepAlive) start the watcher again.
    var EXIT_CODE_CHANGED = 75;
    var EXIT_SESSION_LOST = 1;

    function clone(v) {
        return v === undefined ? undefined : JSON.parse(JSON.stringify(v));
    }

    function initial() {
        return {
            started: false,
            runId: "",
            hostname: "",
            engineHash: "",
            cfg: P.defaults(),
            configKey: "\u0000unloaded",
            session: "up",
            lock: "unknown",
            activity: P.activityReset(0, null),
            presence: "unknown",
            lastPresentAt: null,
            publishedPendingUntil: null,
            seq: 0,
            waits: {},
            inflight: {},
            due: { lock: 0, session: 0, config: 0, code: 0, feed: 0 },
            rawActive: false,
            history: { inputs: [], invalid: [], signals: [] },
            unrecognised: {},
            candidates: {},
            groups: {},
            episodeSeq: 0
        };
    }

    function step(state, event) {
        var s = clone(state);
        var fx = [];
        var at = event.atMs;
        var ctx = { s: s, fx: fx, at: at };
        if (!s.started && event.type !== "start") return { state: state, effects: [] };
        // A timer or helper result that arrives after a suspend must not act
        // before the clock gap has invalidated what was pending.
        if (GAP_CHECKED.indexOf(event.type) >= 0) checkGap(ctx);
        switch (event.type) {
        case "start": onStart(ctx, event); break;
        case "config": applyConfig(ctx, event.text === undefined ? null : event.text); break;
        case "tick": onTick(ctx); break;
        case "input": onInput(ctx, event); break;
        case "surface_closed": applyActivity(ctx, { type: "close", atMs: at }); break;
        case "lock": applyLock(ctx, event.state); break;
        case "session": applySession(ctx, event.state, event.detail); break;
        case "sleep": onSleep(ctx); break;
        case "wake": onWake(ctx); break;
        case "log_line": onLogLine(ctx, event.line); break;
        case "candidate_open": openCandidate(ctx, event); break;
        case "candidate_closed": closeCandidate(ctx, String(event.key), event.closedAtMs || at); break;
        case "helper_done": onHelperDone(ctx, event); break;
        case "observed": onObserved(ctx, event); break;
        case "timer_fired": onTimer(ctx, event.id); break;
        default: log(ctx, "warn", "unknown event " + String(event.type));
        }
        return { state: s, effects: fx };
    }

    var GAP_CHECKED = ["config", "lock", "session", "log_line", "candidate_open", "candidate_closed",
                       "helper_done", "observed", "timer_fired"];

    function checkGap(ctx) {
        var last = ctx.s.activity.lastSeenMs;
        if (last !== null && last !== undefined && Math.abs(ctx.at - last) > P.RESUME_GAP_MS)
            applyActivity(ctx, { type: "tick", atMs: ctx.at });
    }

    // -----------------------------------------------------------------------
    // Effects

    function log(ctx, level, message) {
        ctx.fx.push({ type: "log", level: level, message: message });
    }

    function nextId(ctx, prefix) {
        ctx.s.seq += 1;
        return prefix + ctx.s.seq;
    }

    function setTimer(ctx, delayMs, purpose) {
        var id = nextId(ctx, "t");
        purpose.kind = "timer";
        ctx.s.waits[id] = purpose;
        ctx.fx.push({ type: "set_timer", id: id, delayMs: Math.max(1, Math.round(delayMs)) });
        return id;
    }

    function cancelTimer(ctx, id) {
        if (!id || !ctx.s.waits[id]) return;
        delete ctx.s.waits[id];
        ctx.fx.push({ type: "cancel_timer", id: id });
    }

    function observe(ctx, what, extra) {
        var id = nextId(ctx, "o");
        var wait = extra || {};
        wait.kind = "observe";
        wait.what = what;
        wait.atMs = ctx.at;
        ctx.s.waits[id] = wait;
        var effect = { type: "observe", id: id, what: what };
        if (wait.key !== undefined) effect.key = wait.key;
        ctx.fx.push(effect);
        return id;
    }

    function run(ctx, helper, args, purpose) {
        var id = nextId(ctx, "r");
        purpose.kind = "run";
        ctx.s.waits[id] = purpose;
        ctx.fx.push({ type: "run", id: id, helper: helper, args: args, deadlineMs: DEADLINES[helper] });
        return id;
    }

    // Periodic readings (lock, session, config, code): at most one in flight.
    function poll(ctx, what) {
        var s = ctx.s;
        var current = s.inflight[what];
        if (current && s.waits[current] && ctx.at - s.waits[current].atMs < OBSERVE_STALE_MS) return;
        if (current) {
            delete s.waits[current];
            log(ctx, "warn", "no answer to the " + what + " reading, asking again");
        }
        s.inflight[what] = observe(ctx, what);
    }

    // -----------------------------------------------------------------------
    // Start, config, code

    function onStart(ctx, e) {
        var s = ctx.s;
        s.started = true;
        s.runId = String(e.runId || "");
        s.hostname = String(e.hostname || "");
        s.engineHash = codeHash(e.code) || "unknown";
        var previous = null;
        try {
            previous = e.previousFeed ? JSON.parse(e.previousFeed) : null;
        } catch (err) {
            previous = null;
        }
        s.lastPresentAt = P.restoredLastPresentAt(previous, Math.floor(ctx.at / 1000));
        applyConfig(ctx, e.config === undefined ? null : e.config);
        log(ctx, "info", "started (run " + s.runId + ", engine " + s.engineHash + "), last present "
            + (s.lastPresentAt === null ? "unknown" : P.isoWithOffset(new Date(s.lastPresentAt * 1000))));
        s.history.invalid.push({ fromMs: ctx.at, toMs: null });
        resetInput(ctx, "start");
        writeFeed(ctx);
        observe(ctx, "open_candidates");
        s.due = { lock: ctx.at, session: ctx.at, config: ctx.at + CONFIG_POLL_MS,
                  code: ctx.at + CODE_POLL_MS, feed: ctx.at + FEED_REFRESH_MS };
        poll(ctx, "lock");
        poll(ctx, "session");
        s.due.lock = ctx.at + LOCK_POLL_MS;
        s.due.session = ctx.at + SESSION_POLL_MS;
    }

    function codeHash(code) {
        if (!code || typeof code.policy !== "string" || typeof code.engine !== "string") return null;
        return P.contentHash(code.policy + "\n" + code.engine);
    }

    function applyConfig(ctx, text) {
        var s = ctx.s;
        var key = text === null ? "\u0000missing" : String(text);
        if (key === s.configKey) return;
        s.configKey = key;
        var raw;
        var parseError = false;
        if (text !== null && String(text).trim() !== "") {
            try {
                raw = JSON.parse(text);
            } catch (err) {
                parseError = true;
            }
        }
        var result = P.normaliseConfig(raw, parseError);
        for (var i = 0; i < result.warnings.length; i++) log(ctx, "warn", result.warnings[i]);
        s.cfg = result.config;
        var c = s.cfg;
        var w = c.watcher;
        log(ctx, "info", "config " + (text === null ? "missing, using the defaults" : "loaded") + ": present "
            + c.presence.present_seconds + " s, away " + c.presence.away_seconds + " s, fallback " + w.fallback
            + ", grace " + w.fallback_grace_seconds + " s, expired after " + w.expired_min_seconds
            + " s, confirm after " + w.confirm_seconds + " s, alert states " + c.alerts.presence_states.join("/"));
        recompute(ctx);
    }

    // The host reports the shared files it can read now; new code means a
    // restart, so every machine runs what was pulled.
    function onCode(ctx, result) {
        var hash = codeHash(result);
        if (!hash || hash === ctx.s.engineHash) return;
        log(ctx, "info", "shared code changed (engine " + ctx.s.engineHash + " -> " + hash + "), exiting to restart with it");
        cancelGraces(ctx, "restart for new code");
        ctx.fx.push({ type: "exit", code: EXIT_CODE_CHANGED });
    }

    function machineLabel(s) {
        var configured = s.cfg.machine ? P.sanitiseLabel(s.cfg.machine) : "";
        return configured || P.sanitiseLabel(s.hostname) || "unknown";
    }

    // -----------------------------------------------------------------------
    // Presence

    function onTick(ctx) {
        var s = ctx.s;
        var at = ctx.at;
        applyActivity(ctx, { type: "tick", atMs: at });
        // While the monitor stays active, every second counts as input.
        if (s.rawActive) s.history.inputs.push(at);
        if (at >= s.due.lock) {
            poll(ctx, "lock");
            s.due.lock = at + (anyPending(s) ? LOCK_POLL_PENDING_MS : LOCK_POLL_MS);
        }
        if (at >= s.due.session) {
            poll(ctx, "session");
            s.due.session = at + SESSION_POLL_MS;
        }
        if (at >= s.due.config) {
            poll(ctx, "config");
            s.due.config = at + CONFIG_POLL_MS;
        }
        if (at >= s.due.code) {
            poll(ctx, "code");
            s.due.code = at + CODE_POLL_MS;
        }
        if (at >= s.due.feed) {
            s.due.feed = at + FEED_REFRESH_MS;
            recompute(ctx);
            writeFeed(ctx);
        }
        trimHistory(s, at);
    }

    function trimHistory(s, at) {
        var limit = at - HISTORY_MS;
        var h = s.history;
        while (h.inputs.length && h.inputs[0] < limit) h.inputs.shift();
        while (h.signals.length && h.signals[0].atMs < limit) h.signals.shift();
        while (h.invalid.length && h.invalid[0].toMs !== null && h.invalid[0].toMs < limit) h.invalid.shift();
    }

    function anyPending(s) {
        return Object.keys(s.candidates).length > 0 || Object.keys(s.groups).length > 0;
    }

    function onInput(ctx, e) {
        var s = ctx.s;
        if (e.state === "active") {
            s.history.inputs.push(ctx.at);
            s.rawActive = true;
            applyActivity(ctx, { type: "active", atMs: ctx.at });
            // Resolve held activity on time rather than on the next tick.
            setTimer(ctx, P.CLOSE_WINDOW_MS + 20, { purpose: "activity" });
            setTimer(ctx, P.CONFIRM_MS + 20, { purpose: "activity" });
        } else if (e.state === "idle") {
            s.rawActive = false;
            applyActivity(ctx, { type: "idle", atMs: ctx.at });
        }
        poll(ctx, "lock");
    }

    function applyActivity(ctx, a) {
        var s = ctx.s;
        var wasValid = s.activity.valid;
        var r = P.activityReduce(s.activity, a);
        s.activity = r.state;
        if (r.note === "resume") {
            // Timers stop during suspend; the wall clock does not. The reducer
            // has already dropped anything held before the gap.
            log(ctx, "info", "wall clock jumped (resume or clock change)");
            cancelGraces(ctx, "resume");
            resetInput(ctx, "resume");
            poll(ctx, "lock");
            return;
        }
        if (!wasValid && s.activity.valid) {
            log(ctx, "info", "observations valid");
            var last = s.history.invalid[s.history.invalid.length - 1];
            if (last && last.toMs === null) last.toMs = ctx.at;
        }
        if (r.note === "suspect")
            log(ctx, "info", "activity within " + P.CLOSE_WINDOW_MS + " ms of a window or layer close: held until confirmed");
        else if (r.note === "discarded")
            log(ctx, "info", "held activity discarded as synthetic (idle again within " + P.CONFIRM_MS / 1000 + " s)");
        else if (r.note === "confirmed")
            log(ctx, "info", "held activity confirmed as real input");
        recompute(ctx);
    }

    // A new input monitor: observations are invalid until it reports idle.
    function resetInput(ctx, reason) {
        var s = ctx.s;
        s.activity = P.activityReset(ctx.at, s.activity.lastCloseMs);
        s.rawActive = false;
        var last = s.history.invalid[s.history.invalid.length - 1];
        if (!last || last.toMs !== null) s.history.invalid.push({ fromMs: ctx.at, toMs: null });
        ctx.fx.push({ type: "reset_input" });
        log(ctx, "info", "input monitor (re)created (" + reason + "); observations invalid until 5 s of idleness");
        recompute(ctx);
    }

    function applyLock(ctx, next) {
        var s = ctx.s;
        if (next !== "locked" && next !== "unlocked") next = "unknown";
        if (next !== s.lock) {
            log(ctx, "info", "lock state " + s.lock + " -> " + next);
            s.lock = next;
        }
        recompute(ctx);
    }

    function applySession(ctx, next, detail) {
        var s = ctx.s;
        if (next === "lost") {
            fail(ctx, "session lost" + (detail ? " (" + detail + ")" : ""));
            return;
        }
        if (next !== "up") next = "inactive";
        if (next !== s.session) {
            log(ctx, "info", "session " + s.session + " -> " + next);
            s.session = next;
        }
        recompute(ctx);
    }

    function fail(ctx, reason) {
        var s = ctx.s;
        log(ctx, "warn", reason + "; clearing episodes and exiting");
        cancelGraces(ctx, "session lost");
        s.candidates = {};
        s.groups = {};
        s.session = "lost";
        s.activity = P.activityReset(ctx.at, null);
        recompute(ctx);
        writeFeed(ctx);
        ctx.fx.push({ type: "exit", code: EXIT_SESSION_LOST });
    }

    function onSleep(ctx) {
        log(ctx, "info", "system going to sleep");
        cancelGraces(ctx, "sleep");
    }

    function onWake(ctx) {
        log(ctx, "info", "system woke");
        cancelGraces(ctx, "sleep");
        resetInput(ctx, "wake");
        poll(ctx, "lock");
    }

    function recompute(ctx) {
        var s = ctx.s;
        var previous = s.presence;
        var state = P.derivePresence({
            sessionUp: s.session === "up",
            lock: s.lock,
            activity: s.activity,
            nowMs: ctx.at
        }, s.cfg);
        s.lastPresentAt = P.nextLastPresentAt(previous, state, s.lastPresentAt, Math.floor(ctx.at / 1000));
        s.presence = state;
        var pendingUntil = P.activityPendingUntil(s.activity);
        if (state !== previous) {
            log(ctx, "info", "presence " + previous + " -> " + state);
            writeFeed(ctx);
        } else if (pendingUntil !== s.publishedPendingUntil) {
            // Readers wait while activity is held; tell them at once.
            writeFeed(ctx);
        }
    }

    function writeFeed(ctx) {
        var s = ctx.s;
        s.publishedPendingUntil = P.activityPendingUntil(s.activity);
        ctx.fx.push({ type: "write_feed", document: P.presenceDocument(machineLabel(s), s.presence, ctx.at,
            s.lastPresentAt, s.publishedPendingUntil, s.engineHash) });
    }

    // -----------------------------------------------------------------------
    // 1Password log

    function onLogLine(ctx, line) {
        var s = ctx.s;
        var m = P.matchLogLine(line);
        if (!m) return;
        if (m.signal || m.kind)
            s.history.signals.push({ atMs: m.atMs !== null ? m.atMs : ctx.at, exact: m.atMs !== null, signal: m.signal, kind: m.kind });
        // Log content never leaves the matcher: name the source only, once
        // per source while something is pending.
        if (m.unrecognised && anyPending(s) && !s.unrecognised[m.source]) {
            s.unrecognised[m.source] = true;
            log(ctx, "info", "unrecognised 1Password prompt line from " + m.source);
        }
    }

    // Signals written between fromMs and toMs.
    function signalsBetween(s, fromMs, toMs) {
        var out = [];
        for (var i = 0; i < s.history.signals.length; i++) {
            var sig = s.history.signals[i];
            if (sig.atMs >= fromMs && sig.atMs <= toMs + (sig.exact ? 0 : ARRIVAL_SLACK_MS)) out.push(sig);
        }
        return out;
    }

    // -----------------------------------------------------------------------
    // Candidates and episodes

    function openCandidate(ctx, e) {
        var s = ctx.s;
        var key = String(e.key);
        if (s.candidates[key]) closeCandidate(ctx, key, ctx.at);
        s.seq += 1;
        var c = {
            key: key,
            gen: s.seq,
            openedAtMs: typeof e.openedAtMs === "number" ? e.openedAtMs : ctx.at,
            reconciled: !!e.reconciled,
            source: e.source ? String(e.source) : null,
            kind: P.KINDS.indexOf(e.kind) >= 0 ? e.kind : null,
            confirmed: false,
            episodeId: null,
            groupId: null,
            timer: null
        };
        c.timer = setTimer(ctx, s.cfg.watcher.confirm_seconds * 1000, { purpose: "confirm", key: key, gen: c.gen });
        s.candidates[key] = c;
        s.due.lock = Math.min(s.due.lock, ctx.at + LOCK_POLL_PENDING_MS);
    }

    function currentCandidate(s, key, gen) {
        var c = s.candidates[key];
        return c && c.gen === gen ? c : null;
    }

    function reject(ctx, c, reason) {
        log(ctx, "info", "candidate window" + (c.source ? " (" + c.source + ")" : "")
            + (c.reconciled ? ", reconciled," : "") + " is not an approval: " + reason);
        cancelTimer(ctx, c.timer);
        delete ctx.s.candidates[c.key];
        if (!anyPending(ctx.s)) ctx.s.unrecognised = {};
    }

    function onCandidateChecked(ctx, wait, result) {
        var s = ctx.s;
        var c = currentCandidate(s, wait.key, wait.gen);
        if (!c) return;
        if (!result || !result.confirmed) {
            reject(ctx, c, result && result.reason ? String(result.reason) : "confirmation failed");
            return;
        }
        // The system Touch ID dialog belongs to 1Password only when
        // 1Password asked for an unlock just before it opened.
        if (c.source === "system-auth" && !c.reconciled) {
            var unlock = signalsBetween(s, c.openedAtMs - P.UNLOCK_LINE_MS, c.openedAtMs).some(function (sig) {
                return sig.signal === "unlock";
            });
            if (!unlock) {
                reject(ctx, c, "no 1Password unlock request");
                return;
            }
            c.kind = P.mergeKind(c.kind, "unlock");
        }
        startEpisode(ctx, c, result.kind);
    }

    // The groups an episode opened at openedAtMs overlaps, oldest first: any
    // with a window still open, and any whose last window closed after it
    // opened and that is not yet classified.
    function overlappingGroups(s, openedAtMs) {
        return Object.keys(s.groups).map(function (id) { return s.groups[id]; }).filter(function (g) {
            return g.openMembers > 0 || (g.phase === "settling" && g.closedAtMs >= openedAtMs);
        }).sort(function (a, b) { return a.openedAtMs - b.openedAtMs; });
    }

    // Moves every episode of `from` into `into`: a late confirmation can
    // bridge two groups that each overlap it.
    function mergeGroup(ctx, into, from) {
        var s = ctx.s;
        cancelTimer(ctx, from.timer);
        from.order.forEach(function (id) {
            into.episodes[id] = from.episodes[id];
            into.order.push(id);
        });
        into.order.sort(function (a, b) { return into.episodes[a].openedAtMs - into.episodes[b].openedAtMs; });
        into.openMembers += from.openMembers;
        into.openedAtMs = Math.min(into.openedAtMs, from.openedAtMs);
        into.closedAtMs = Math.max(into.closedAtMs || 0, from.closedAtMs || 0) || null;
        Object.keys(s.candidates).forEach(function (key) {
            if (s.candidates[key].groupId === from.id) s.candidates[key].groupId = into.id;
        });
        Object.keys(s.waits).forEach(function (id) {
            if (s.waits[id].groupId === from.id) s.waits[id].groupId = into.id;
        });
        delete s.groups[from.id];
        log(ctx, "info", "episode " + from.id + " merged into episode " + into.id);
    }

    // An unconfirmed candidate that opened before the group closed may still
    // join it.
    function awaitingConfirmation(s, group) {
        return Object.keys(s.candidates).some(function (key) {
            var c = s.candidates[key];
            return !c.confirmed && c.openedAtMs <= group.closedAtMs;
        });
    }

    function startEpisode(ctx, c, kind) {
        var s = ctx.s;
        s.episodeSeq += 1;
        c.confirmed = true;
        c.episodeId = s.runId + "-" + s.episodeSeq;
        c.kind = P.mergeKind(c.kind, kind);
        var overlapping = overlappingGroups(s, c.openedAtMs);
        var group = overlapping[0] || null;
        for (var i = 1; i < overlapping.length; i++) mergeGroup(ctx, group, overlapping[i]);
        if (group) {
            log(ctx, "info", "episode " + c.episodeId + " started" + (c.reconciled ? " (reconciled)" : "")
                + ", overlapping episode " + group.id + ": merged");
            cancelTimer(ctx, group.timer);
            group.timer = null;
            group.phase = "open";
        } else {
            group = { id: c.episodeId, episodes: {}, order: [], openMembers: 0, openedAtMs: c.openedAtMs,
                      closedAtMs: null, timer: null, phase: "open", facts: null, expiredAt: null,
                      fallbackAttempted: false, cancelled: false };
            s.groups[group.id] = group;
            log(ctx, "info", "episode " + c.episodeId + " started" + (c.reconciled ? " (reconciled, never fallback-eligible)" : "")
                + (c.source ? " (" + c.source + ")" : ""));
        }
        c.groupId = group.id;
        group.openMembers += 1;
        group.openedAtMs = Math.min(group.openedAtMs, c.openedAtMs);
        group.episodes[c.episodeId] = {
            id: c.episodeId, openedAtMs: c.openedAtMs, closedAtMs: null, reconciled: c.reconciled,
            kind: c.kind, requesters: null, pid: null, process: "", identity: null
        };
        group.order.push(c.episodeId);
        var args = c.reconciled ? ["--reconciled"] : ["--opened-at", (c.openedAtMs / 1000).toFixed(3)];
        run(ctx, "requesters", args, { purpose: "requesters", groupId: group.id, episodeId: c.episodeId });
    }

    function episodeOf(s, wait) {
        var g = s.groups[wait.groupId];
        return g ? g.episodes[wait.episodeId] || null : null;
    }

    function parseJson(text) {
        try {
            return JSON.parse(String(text || "").trim());
        } catch (err) {
            return null;
        }
    }

    function onRequesters(ctx, wait, e) {
        var ep = episodeOf(ctx.s, wait);
        if (!ep) return;
        var result = e.code === 0 ? parseJson(e.output) : null;
        if (!result) {
            log(ctx, "info", "episode " + ep.id + ": requester check failed (exit " + e.code + "), the fallback names the machine only");
            return;
        }
        var outcome = P.requesterOutcome(result);
        ep.requesters = outcome.count;
        ep.kind = P.mergeKind(ep.kind, outcome.kind);
        var sources = {};
        result.candidates.forEach(function (r) { sources[r.source] = (sources[r.source] || 0) + 1; });
        log(ctx, "info", "episode " + ep.id + ": " + outcome.count + " requester candidate(s) " + JSON.stringify(sources));
        if (outcome.pid === null) {
            if (outcome.count > 1) log(ctx, "info", "episode " + ep.id + ": several requesters, the fallback names the machine only");
            return;
        }
        ep.pid = outcome.pid;
        ep.process = outcome.comm;
        // Identify now: the requester may exit before the fallback is due.
        run(ctx, "locate", ["--pid", String(outcome.pid)], { purpose: "locate", groupId: wait.groupId, episodeId: ep.id });
    }

    function onLocate(ctx, wait, e) {
        var ep = episodeOf(ctx.s, wait);
        if (!ep) return;
        var identity = e.code === 0 ? parseJson(e.output) : null;
        if (identity && typeof identity === "object" && !Array.isArray(identity)) {
            ep.identity = identity;
            log(ctx, "info", "episode " + ep.id + ": requester identified");
        } else {
            log(ctx, "info", "episode " + ep.id + ": requester not identified (locate exit " + e.code + ")");
        }
    }

    function closeCandidate(ctx, key, closedAtMs) {
        var s = ctx.s;
        var c = s.candidates[key];
        if (!c) return;
        delete s.candidates[key];
        cancelTimer(ctx, c.timer);
        if (!c.confirmed) {
            log(ctx, "info", "candidate window" + (c.source ? " (" + c.source + ")" : "") + " closed before confirmation");
            if (!anyPending(s)) s.unrecognised = {};
            return;
        }
        var group = s.groups[c.groupId];
        if (!group) return;
        var ep = group.episodes[c.episodeId];
        ep.closedAtMs = closedAtMs;
        // A monitor still active counts as input up to the close.
        if (s.rawActive) s.history.inputs.push(closedAtMs);
        group.openMembers -= 1;
        group.closedAtMs = Math.max(group.closedAtMs || 0, closedAtMs);
        log(ctx, "info", "episode " + ep.id + " closed" + (c.reconciled ? "" : " after " + ((closedAtMs - ep.openedAtMs) / 1000).toFixed(1) + " s"));
        if (group.openMembers === 0) {
            group.phase = "settling";
            group.timer = setTimer(ctx, CLOSE_SETTLE_MS, { purpose: "settle", groupId: group.id });
        }
    }

    // -----------------------------------------------------------------------
    // Outcome and fallback

    function episodeFacts(s, ep) {
        var open = ep.openedAtMs;
        var close = ep.closedAtMs;
        var signal = null;
        var kind = ep.kind;
        signalsBetween(s, open, close).forEach(function (sig) {
            if ((sig.signal === "timeout" || sig.signal === "cancel") && !signal) signal = sig.signal;
            kind = P.mergeKind(kind, sig.kind);
        });
        var inputSeen = s.history.inputs.some(function (t) { return t > open && t <= close; });
        var covered = !s.history.invalid.some(function (gap) {
            return gap.fromMs <= close && (gap.toMs === null || gap.toMs >= open);
        });
        return { reconciled: ep.reconciled, lifetimeMs: close - open, signal: signal,
                 covered: covered, inputSeen: inputSeen, kind: kind };
    }

    function settleGroup(ctx, group) {
        var s = ctx.s;
        group.timer = null;
        if (awaitingConfirmation(s, group)) {
            group.timer = setTimer(ctx, CLOSE_SETTLE_MS, { purpose: "settle", groupId: group.id });
            return;
        }
        group.phase = "classified";
        var kind = null;
        group.facts = group.order.map(function (id) {
            var facts = episodeFacts(s, group.episodes[id]);
            kind = P.mergeKind(kind, facts.kind);
            return facts;
        });
        group.kind = kind || "unknown";
        var classification = P.classifyGroup(group.facts, s.cfg);
        var lifetime = ((group.closedAtMs - group.openedAtMs) / 1000).toFixed(1);
        log(ctx, "info", "episode " + group.id + " ended: " + classification.outcome.replace("_", " ") + " ("
            + classification.reason + "), " + group.kind + (classification.outcome === "reconciled" ? "" : ", after " + lifetime + " s"));
        recompute(ctx);
        var grace = P.graceEligible(group, classification, s.presence, s.cfg);
        if (!grace.eligible) {
            if (classification.outcome === "not_given") log(ctx, "info", "episode " + group.id + ": no fallback (" + grace.reason + ")");
            finishGroup(ctx, group);
            return;
        }
        group.expiredAt = Math.floor(group.closedAtMs / 1000);
        group.phase = "grace";
        log(ctx, "info", "episode " + group.id + ": " + grace.reason + ", fallback in "
            + s.cfg.watcher.fallback_grace_seconds + " s unless Rod returns");
        group.timer = setTimer(ctx, s.cfg.watcher.fallback_grace_seconds * 1000, { purpose: "grace", groupId: group.id });
    }

    function finishGroup(ctx, group) {
        cancelTimer(ctx, group.timer);
        delete ctx.s.groups[group.id];
        if (!anyPending(ctx.s)) ctx.s.unrecognised = {};
    }

    // Cancels every fallback that is waiting for its grace period or for
    // the claim; one already publishing is left to finish.
    function cancelGraces(ctx, reason) {
        var s = ctx.s;
        Object.keys(s.groups).forEach(function (id) {
            var g = s.groups[id];
            if (g.phase === "grace") {
                log(ctx, "info", "episode " + g.id + ": fallback cancelled (" + reason + ")");
                finishGroup(ctx, g);
            } else if (g.phase === "claiming" && !g.cancelled) {
                g.cancelled = true;
                log(ctx, "info", "episode " + g.id + ": fallback cancelled (" + reason + ")");
            }
        });
    }

    function onGrace(ctx, group) {
        var s = ctx.s;
        group.timer = null;
        if (s.activity.pending) {
            log(ctx, "info", "episode " + group.id + ": fallback waits for held activity to resolve");
            group.timer = setTimer(ctx, P.CONFIRM_MS + 500, { purpose: "grace", groupId: group.id });
            return;
        }
        recompute(ctx);
        var decision = P.fallbackDecision(group, s.presence, s.lastPresentAt, s.cfg);
        if (!decision.send) {
            log(ctx, "info", "episode " + group.id + ": no fallback (" + decision.reason + ")");
            finishGroup(ctx, group);
            return;
        }
        // At most one attempt per group, whatever happens next. No retry.
        group.fallbackAttempted = true;
        group.phase = "claiming";
        run(ctx, "claim", ["take", "--source", "watcher", "--expired-at", String(group.expiredAt), "--require-away"],
            { purpose: "claim", groupId: group.id });
    }

    // Names one requester only when the whole group had exactly one.
    function fallbackIdentity(group) {
        var named = null;
        var count = 0;
        group.order.forEach(function (id) {
            var ep = group.episodes[id];
            if (ep.requesters) count += ep.requesters;
            if (ep.identity && !named) named = ep;
        });
        if (count !== 1 || !named) return {};
        var identity = {};
        ["machine", "harness", "project", "location"].forEach(function (k) {
            if (typeof named.identity[k] === "string") identity[k] = named.identity[k];
        });
        if (named.process) identity.process = named.process;
        return identity;
    }

    function onClaim(ctx, wait, e) {
        var group = ctx.s.groups[wait.groupId];
        if (!group) return;
        var answer = String(e.output || "").trim().split("\n")[0];
        if (group.cancelled) {
            log(ctx, "info", "episode " + group.id + ": claim " + (e.code === 0 ? "granted" : "refused") + " after the fallback was cancelled, not publishing");
            finishGroup(ctx, group);
            return;
        }
        if (e.code !== 0) {
            log(ctx, "info", "episode " + group.id + ": claim refused (exit " + e.code + (answer ? ": " + answer : "") + "), no fallback");
            finishGroup(ctx, group);
            return;
        }
        log(ctx, "info", "episode " + group.id + ": claim granted, publishing the fallback");
        group.phase = "publishing";
        run(ctx, "publish", ["--template", "fallback", "--identity", JSON.stringify(fallbackIdentity(group)),
            "--category", group.kind], { purpose: "publish", groupId: group.id });
    }

    function onPublish(ctx, wait, e) {
        var group = ctx.s.groups[wait.groupId];
        var out = parseJson(e.output);
        var result = out && out.result ? out.result : "failed";
        var detail = out ? (out.reason || (out.http_status !== undefined ? "HTTP " + out.http_status
            + (out.curl_exit ? ", curl exit " + out.curl_exit : "") : "")) : "no output";
        log(ctx, "info", "episode " + wait.groupId + ": fallback " + result + " (exit " + e.code + (detail ? ", " + detail : "") + ")");
        if (group) finishGroup(ctx, group);
    }

    // -----------------------------------------------------------------------
    // Host answers

    function onHelperDone(ctx, e) {
        var wait = ctx.s.waits[e.id];
        if (!wait || wait.kind !== "run") return;
        delete ctx.s.waits[e.id];
        if (wait.purpose === "requesters") onRequesters(ctx, wait, e);
        else if (wait.purpose === "locate") onLocate(ctx, wait, e);
        else if (wait.purpose === "claim") onClaim(ctx, wait, e);
        else if (wait.purpose === "publish") onPublish(ctx, wait, e);
    }

    function onObserved(ctx, e) {
        var s = ctx.s;
        var wait = s.waits[e.id];
        if (!wait || wait.kind !== "observe") return;
        delete s.waits[e.id];
        if (s.inflight[wait.what] === e.id) delete s.inflight[wait.what];
        var r = e.result;
        if (wait.what === "candidate") onCandidateChecked(ctx, wait, r);
        else if (wait.what === "open_candidates") onOpenCandidates(ctx, r);
        else if (wait.what === "lock") applyLock(ctx, r && r.state);
        else if (wait.what === "session") applySession(ctx, r && r.state, r && r.detail);
        else if (wait.what === "config") applyConfig(ctx, r && typeof r.text === "string" ? r.text : null);
        else if (wait.what === "code") onCode(ctx, r);
    }

    // Approvals already open at start: unknown age, same confirmation,
    // never fallback-eligible.
    function onOpenCandidates(ctx, r) {
        var list = r && Array.isArray(r.candidates) ? r.candidates : [];
        list.forEach(function (c) {
            if (c && c.key !== undefined && !ctx.s.candidates[String(c.key)])
                openCandidate(ctx, { key: c.key, openedAtMs: ctx.at, reconciled: true, source: c.source, kind: c.kind });
        });
        log(ctx, "info", "reconciled " + list.length + " approval window(s) already open"
            + (r && r.detail ? " (" + r.detail + ")" : ""));
    }

    function onTimer(ctx, id) {
        var s = ctx.s;
        var wait = s.waits[id];
        if (!wait || wait.kind !== "timer") return;
        delete s.waits[id];
        if (wait.purpose === "activity") {
            applyActivity(ctx, { type: "tick", atMs: ctx.at });
        } else if (wait.purpose === "confirm") {
            var c = currentCandidate(s, wait.key, wait.gen);
            if (!c) return;
            c.timer = null;
            observe(ctx, "candidate", { key: c.key, gen: c.gen });
        } else if (wait.purpose === "settle") {
            var g = s.groups[wait.groupId];
            if (g) settleGroup(ctx, g);
        } else if (wait.purpose === "grace") {
            var group = s.groups[wait.groupId];
            if (group) onGrace(ctx, group);
        }
    }

    return { initial: initial, step: step };
}

if (typeof module !== "undefined") module.exports = { createEngine: createEngine };
