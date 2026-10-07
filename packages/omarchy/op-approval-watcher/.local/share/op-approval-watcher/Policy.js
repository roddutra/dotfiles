// Decision rules for the 1Password approval watcher. Pure functions with no
// QML or I/O, so shell.qml imports this file unchanged and node can test it.
// No `.pragma library`: node would reject it, and the functions keep no state.

var WINDOW_CLASS = "com.onepassword.OnePassword";
var WINDOW_TITLE = "1Password";
var STATES = ["present", "idle", "away", "locked", "unknown"];

function defaults() {
    return {
        machine: null,
        alerts: { presence_states: ["idle", "away", "locked", "unknown"] },
        presence: { present_seconds: 60, away_seconds: 300 },
        watcher: {
            fallback: true,
            fallback_grace_seconds: 120,
            expired_min_seconds: 59,
            confirm_seconds: 1
        }
    };
}

// ---------------------------------------------------------------------------
// Configuration

function isObject(v) {
    return v !== null && typeof v === "object" && !Array.isArray(v);
}

function isInt(v) {
    return typeof v === "number" && isFinite(v) && Math.floor(v) === v;
}

// Mirrors the validation in the shared library (common.sh): a missing value
// takes its default silently, an invalid one takes its default with a
// warning. Only the keys the watcher uses are read; others are ignored.
// raw is the parsed JSON (undefined for an empty file); parseError is set
// when the file is not valid JSON.
function normaliseConfig(raw, parseError) {
    var config = defaults();
    var warnings = [];
    if (parseError) {
        warnings.push("config.json is not valid JSON, using the defaults");
        return { config: config, warnings: warnings };
    }
    if (raw === undefined) return { config: config, warnings: warnings };
    if (!isObject(raw)) {
        warnings.push("config.json is not a JSON object, using the defaults");
        return { config: config, warnings: warnings };
    }

    function field(path, valid, apply) {
        var v = raw;
        for (var i = 0; i < path.length; i++) {
            if (v === null || v === undefined) { v = null; break; }
            if (!isObject(v)) { v = undefined; break; }
            v = Object.prototype.hasOwnProperty.call(v, path[i]) ? v[path[i]] : null;
        }
        if (v === null) return;
        if (v !== undefined && valid(v)) {
            apply(v);
            return;
        }
        warnings.push("invalid " + path.join(".") + " in config.json, using the default");
    }

    field(["machine"], function (v) { return typeof v === "string" && v.length > 0; },
        function (v) { config.machine = v; });
    field(["alerts", "presence_states"], function (v) {
        return Array.isArray(v) && v.every(function (s) { return STATES.indexOf(s) >= 0; });
    }, function (v) { config.alerts.presence_states = v.slice(); });
    field(["presence", "present_seconds"], function (v) { return isInt(v) && v >= 1; },
        function (v) { config.presence.present_seconds = v; });
    field(["presence", "away_seconds"], function (v) { return isInt(v) && v >= 1; },
        function (v) { config.presence.away_seconds = v; });
    field(["watcher", "fallback"], function (v) { return typeof v === "boolean"; },
        function (v) { config.watcher.fallback = v; });
    field(["watcher", "fallback_grace_seconds"], function (v) { return isInt(v) && v >= 0; },
        function (v) { config.watcher.fallback_grace_seconds = v; });
    field(["watcher", "expired_min_seconds"], function (v) { return isInt(v) && v >= 1; },
        function (v) { config.watcher.expired_min_seconds = v; });
    field(["watcher", "confirm_seconds"], function (v) { return typeof v === "number" && isFinite(v) && v > 0; },
        function (v) { config.watcher.confirm_seconds = v; });

    if (config.presence.away_seconds <= config.presence.present_seconds) {
        var d = defaults().presence;
        warnings.push("presence.away_seconds must be greater than presence.present_seconds, using the defaults for both");
        config.presence.present_seconds = d.present_seconds;
        config.presence.away_seconds = d.away_seconds;
    }
    return { config: config, warnings: warnings };
}

// Same allowlist as opa_sanitise in common.sh: [A-Za-z0-9 ._:/@+-], spaces
// collapsed, at most 40 bytes.
function sanitiseLabel(text) {
    var s = String(text === undefined || text === null ? "" : text)
        .replace(/[\t\n\r]/g, " ")
        .replace(/[^A-Za-z0-9 ._:\/@+-]/g, "")
        .replace(/ +/g, " ")
        .replace(/^ /, "")
        .slice(0, 40)
        .replace(/ $/, "");
    return s;
}

// ---------------------------------------------------------------------------
// Hyprland window events

// socket2 addresses carry no 0x prefix; hyprctl's JSON does.
function addressKey(address) {
    return String(address || "").toLowerCase().replace(/^0x/, "");
}

// Parses the data of openwindow (ADDR,WORKSPACE,CLASS,TITLE),
// windowtitlev2 (ADDR,TITLE) and closewindow (ADDR). Titles may contain
// commas, so only the leading fields are split off. Returns null for other
// events or malformed data.
function parseWindowEvent(name, data) {
    data = String(data === undefined || data === null ? "" : data);
    function take(n) {
        var parts = [];
        var rest = data;
        for (var i = 0; i < n - 1; i++) {
            var at = rest.indexOf(",");
            if (at < 0) return null;
            parts.push(rest.slice(0, at));
            rest = rest.slice(at + 1);
        }
        parts.push(rest);
        return parts;
    }
    var p;
    if (name === "openwindow") {
        p = take(4);
        if (!p || !p[0]) return null;
        return { type: "open", address: addressKey(p[0]), workspace: p[1], windowClass: p[2], title: p[3] };
    }
    if (name === "windowtitlev2") {
        p = take(2);
        if (!p || !p[0]) return null;
        return { type: "title", address: addressKey(p[0]), title: p[1] };
    }
    if (name === "closewindow") {
        if (!data) return null;
        return { type: "close", address: addressKey(data) };
    }
    return null;
}

function isApprovalClass(windowClass) {
    return windowClass === WINDOW_CLASS;
}

function isApprovalTitle(title) {
    return title === WINDOW_TITLE;
}

// The 1 s re-check (D2). candidate: {address, closed, titleChanged};
// clients: parsed `hyprctl clients -j`. The window must still be open at that
// address with the 1Password class and the exact title `1Password`, and its
// title must never have changed since it opened (the main window renames
// itself within about 0.3 s; Quick Access and Settings have other titles).
function confirmCandidate(candidate, clients) {
    if (candidate.closed) return { confirmed: false, reason: "closed before confirmation" };
    if (candidate.titleChanged) return { confirmed: false, reason: "title changed" };
    if (!Array.isArray(clients)) return { confirmed: false, reason: "client list unavailable" };
    var client = null;
    for (var i = 0; i < clients.length; i++) {
        if (clients[i] && addressKey(clients[i].address) === candidate.address) {
            client = clients[i];
            break;
        }
    }
    if (!client) return { confirmed: false, reason: "window not found" };
    if (!isApprovalClass(client["class"])) return { confirmed: false, reason: "class differs" };
    if (!isApprovalTitle(client.title)) return { confirmed: false, reason: "title differs" };
    return { confirmed: true, reason: "title still 1Password" };
}

// D2/D3: a confirmed window is an episode only with at least one requester
// candidate. One candidate can be named; several cannot.
function requesterOutcome(result) {
    var list = result && Array.isArray(result.candidates) ? result.candidates : [];
    if (list.length === 0) return { episode: false, count: 0, pid: null };
    return { episode: true, count: list.length, pid: list.length === 1 ? list[0].pid : null };
}

// How an episode ended. Reconciled episodes (already open at start) have an
// unknown age and are never treated as expired.
function classifyEnd(episode, closedAtMs, config) {
    if (episode.reconciled) return "reconciled";
    var lifetime = (closedAtMs - episode.openedAtMs) / 1000;
    return lifetime >= config.watcher.expired_min_seconds ? "expired" : "answered";
}

// ---------------------------------------------------------------------------
// Presence

// Activity comes from one 5 s idle monitor (ext-idle-notify v2): "idle" means
// no input for 5 s, "active" means input again. Idle and away are measured on
// the wall clock from the last real input, not by longer idle monitors.
//
// Hyprland reports activity when a window or layer closes (pointer focus moves
// to another surface) even with nobody at the PC. So an idle -> active
// transition within CLOSE_WINDOW_MS of a closewindow or closelayer event, on
// either side, is suspect: it changes nothing until it is confirmed. It is
// discarded as synthetic if the monitor is idle again within CONFIRM_MS of it
// (a single synthetic event lets the 5 s monitor expire), and confirmed as
// real if the monitor is still active after CONFIRM_MS. Any other activity is
// applied once CLOSE_WINDOW_MS has passed without a close event.
//
// The watcher sends a tick every second. A gap of more than RESUME_GAP_MS
// between events means the PC was suspended (or the clock moved): the next
// event, whatever it is, only resets the state, so activity held before the
// suspend can never be confirmed by a late timer after it.
var CLOSE_WINDOW_MS = 300;
var CONFIRM_MS = 5500;
var RESUME_GAP_MS = 5000;
var VALIDITY_SECONDS = 5;

// After (re)creating the monitor: nothing is known until the monitor reports
// idle once. lastInputMs is then only an upper bound (no input since atMs).
function activityReset(atMs, lastCloseMs) {
    return { valid: false, active: false, inputKnown: false, lastInputMs: atMs,
             lastCloseMs: lastCloseMs === undefined ? null : lastCloseMs, pending: null,
             lastSeenMs: atMs };
}

function copyActivity(s) {
    return { valid: s.valid, active: s.active, inputKnown: s.inputKnown, lastInputMs: s.lastInputMs,
             lastCloseMs: s.lastCloseMs,
             pending: s.pending ? { atMs: s.pending.atMs, suspect: s.pending.suspect } : null,
             lastSeenMs: s.lastSeenMs };
}

// When held activity will be confirmed or applied at the latest (epoch ms),
// or null when nothing is held. Published in the feed so readers can wait.
function activityPendingUntil(s) {
    if (!s.pending) return null;
    return s.pending.atMs + (s.pending.suspect ? CONFIRM_MS : CLOSE_WINDOW_MS);
}

function nearClose(atMs, lastCloseMs) {
    return lastCloseMs !== null && Math.abs(atMs - lastCloseMs) <= CLOSE_WINDOW_MS;
}

// Applies one event and returns {state, note}; note names a suspect,
// discarded or confirmed activity, or a resume, for the log, else null.
// Events:
//   {type: "close", atMs}   closewindow or closelayer
//   {type: "active", atMs}  the 5 s monitor reported input
//   {type: "idle", atMs}    the 5 s monitor reported 5 s without input
//   {type: "tick", atMs}    time passes (resolves pending activity)
function activityReduce(state, event) {
    var at = event.atMs;
    if (state.lastSeenMs !== undefined && state.lastSeenMs !== null && Math.abs(at - state.lastSeenMs) > RESUME_GAP_MS)
        return { state: activityReset(at, state.lastCloseMs), note: "resume" };
    var s = copyActivity(state);
    s.lastSeenMs = at;
    var note = null;
    if (event.type === "close") {
        s.lastCloseMs = at;
        if (s.pending && !s.pending.suspect && nearClose(s.pending.atMs, at)) {
            s.pending.suspect = true;
            note = "suspect";
        }
    } else if (event.type === "active") {
        if (s.valid && !s.active && !s.pending) {
            s.pending = { atMs: at, suspect: nearClose(at, s.lastCloseMs) };
            if (s.pending.suspect) note = "suspect";
        }
    } else if (event.type === "idle") {
        if (!s.valid) {
            // No input for the last 5 s; any input since the reset was before
            // that and went unobserved, so idleness is only known from here.
            s.valid = true;
            s.lastInputMs = at - VALIDITY_SECONDS * 1000;
        } else if (s.pending) {
            if (s.pending.suspect && at - s.pending.atMs <= CONFIRM_MS) {
                note = "discarded";
            } else {
                // Real input that already stopped: last input 5 s ago.
                s.inputKnown = true;
                s.lastInputMs = Math.max(s.pending.atMs, at - VALIDITY_SECONDS * 1000);
                if (s.pending.suspect) note = "confirmed";
            }
            s.pending = null;
            s.active = false;
        } else if (s.active) {
            s.active = false;
            s.lastInputMs = at - VALIDITY_SECONDS * 1000;
        }
    } else if (event.type === "tick") {
        if (s.pending) {
            var age = at - s.pending.atMs;
            if (s.pending.suspect ? age >= CONFIRM_MS : age >= CLOSE_WINDOW_MS) {
                if (s.pending.suspect) note = "confirmed";
                s.pending = null;
                s.active = true;
                s.inputKnown = true;
                s.lastInputMs = at;
            }
        } else if (s.active) {
            s.lastInputMs = at;
        }
    }
    return { state: s, note: note };
}

// obs: {hyprlandUp, lock: "locked"|"unlocked"|"unknown", activity (from
// activityReduce), nowMs}. Until real input has been seen since the monitor
// was created, the time since creation is only a lower bound on idleness: it
// can show idle or away, never present.
function derivePresence(obs, config) {
    if (!obs.hyprlandUp) return "unknown";
    if (obs.lock === "locked") return "locked";
    if (obs.lock !== "unlocked") return "unknown";
    var a = obs.activity;
    if (!a.valid) return "unknown";
    if (a.active) return "present";
    var idleSeconds = (obs.nowMs - a.lastInputMs) / 1000;
    if (idleSeconds >= config.presence.away_seconds) return "away";
    if (idleSeconds >= config.presence.present_seconds) return "idle";
    return a.inputKnown ? "present" : "unknown";
}

// last_present_at is the latest moment presence was observed as present:
// now while present, and the moment it stopped being present.
function nextLastPresentAt(previousState, state, lastPresentAt, nowSec) {
    if (state === "present" || previousState === "present") return nowSec;
    return lastPresentAt;
}

// last_present_at carried over from the previous feed on start: a positive
// epoch not in the future, else null.
function restoredLastPresentAt(previousFeed, nowSec) {
    var v = previousFeed && isObject(previousFeed) ? previousFeed.last_present_at : null;
    if (typeof v !== "number" || !isFinite(v) || v <= 0 || v > nowSec) return null;
    return Math.floor(v);
}

function pad2(n) {
    return (n < 10 ? "0" : "") + n;
}

// ISO 8601 local time with offset, e.g. 2026-10-07T15:02:11+10:00.
function isoWithOffset(date) {
    var off = -date.getTimezoneOffset();
    var sign = off >= 0 ? "+" : "-";
    off = Math.abs(off);
    return date.getFullYear() + "-" + pad2(date.getMonth() + 1) + "-" + pad2(date.getDate())
        + "T" + pad2(date.getHours()) + ":" + pad2(date.getMinutes()) + ":" + pad2(date.getSeconds())
        + sign + pad2(Math.floor(off / 60)) + ":" + pad2(off % 60);
}

// pendingUntilMs: activityPendingUntil, published as activity_pending_until
// (epoch seconds, rounded up) only while activity is held.
function presenceDocument(machine, state, nowMs, lastPresentAt, pendingUntilMs) {
    var doc = {
        machine: machine,
        state: state,
        updated_at: isoWithOffset(new Date(nowMs)),
        updated_epoch: Math.floor(nowMs / 1000),
        last_present_at: lastPresentAt === null || lastPresentAt === undefined ? null : lastPresentAt
    };
    if (pendingUntilMs !== null && pendingUntilMs !== undefined)
        doc.activity_pending_until = Math.ceil(pendingUntilMs / 1000);
    return doc;
}

// ---------------------------------------------------------------------------
// Fallback (decision 10, D2, D10)

function stateAlerts(state, config) {
    return state !== "present" && config.alerts.presence_states.indexOf(state) >= 0;
}

// At closewindow: start the grace timer only for an expired, non-reconciled
// episode while Rod is not present.
function graceEligible(episode, classification, state, config) {
    if (classification !== "expired") return { eligible: false, reason: classification };
    if (episode.reconciled) return { eligible: false, reason: "reconciled" };
    if (!config.watcher.fallback) return { eligible: false, reason: "fallback disabled" };
    if (episode.fallbackAttempted) return { eligible: false, reason: "already attempted" };
    if (state === "present") return { eligible: false, reason: "present at expiry" };
    if (!stateAlerts(state, config)) return { eligible: false, reason: "presence " + state + " excluded by alerts.presence_states" };
    return { eligible: true, reason: "expired while " + state };
}

// When the grace timer fires, against the config in force then: the episode
// must still classify as expired (its open-to-close lifetime against the
// current expired_min_seconds), Rod must still not be present and must not
// have been present at any point since the expiry (any return cancels, even
// if he left again). The shared claim (D10) is taken after this.
function fallbackDecision(episode, state, lastPresentAt, config) {
    var classification = classifyEnd(episode, episode.closedAtMs, config);
    if (classification !== "expired") return { send: false, reason: classification + " under the current config" };
    if (episode.fallbackAttempted) return { send: false, reason: "already attempted" };
    if (!config.watcher.fallback) return { send: false, reason: "fallback disabled" };
    if (state === "present") return { send: false, reason: "present" };
    if (!stateAlerts(state, config)) return { send: false, reason: "presence " + state + " excluded by alerts.presence_states" };
    if (lastPresentAt !== null && lastPresentAt !== undefined && lastPresentAt >= episode.expiredAt)
        return { send: false, reason: "present since the expiry" };
    return { send: true, reason: "still not present" };
}

if (typeof module !== "undefined") {
    module.exports = {
        WINDOW_CLASS: WINDOW_CLASS,
        WINDOW_TITLE: WINDOW_TITLE,
        defaults: defaults,
        normaliseConfig: normaliseConfig,
        sanitiseLabel: sanitiseLabel,
        addressKey: addressKey,
        parseWindowEvent: parseWindowEvent,
        isApprovalClass: isApprovalClass,
        isApprovalTitle: isApprovalTitle,
        confirmCandidate: confirmCandidate,
        requesterOutcome: requesterOutcome,
        classifyEnd: classifyEnd,
        CLOSE_WINDOW_MS: CLOSE_WINDOW_MS,
        CONFIRM_MS: CONFIRM_MS,
        activityReset: activityReset,
        activityPendingUntil: activityPendingUntil,
        activityReduce: activityReduce,
        derivePresence: derivePresence,
        nextLastPresentAt: nextLastPresentAt,
        restoredLastPresentAt: restoredLastPresentAt,
        isoWithOffset: isoWithOffset,
        presenceDocument: presenceDocument,
        graceEligible: graceEligible,
        fallbackDecision: fallbackDecision
    };
}
