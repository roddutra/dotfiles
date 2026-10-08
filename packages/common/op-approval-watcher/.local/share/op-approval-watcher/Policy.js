// Decision rules for the 1Password approval watcher, shared by every platform.
// Pure functions with no I/O, written in the JavaScript subset that runs
// unchanged in Quickshell's QML engine, JavaScriptCore and node. No
// `.pragma library` and no modules: node would reject the pragma, and the
// functions keep no state. Engine.js receives these functions as the POLICY
// object at the end of this file.

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

// Requesters add identity only: one candidate can be named, several cannot.
// Their sources also hint at the approval type.
function requesterOutcome(result) {
    var list = result && Array.isArray(result.candidates) ? result.candidates : [];
    var kind = null;
    for (var i = 0; i < list.length; i++) {
        var k = list[i] && list[i].source === "ssh-agent" ? "ssh" : list[i] && list[i].source === "op" ? "op-cli" : null;
        kind = mergeKind(kind, k);
    }
    return {
        count: list.length,
        pid: list.length === 1 ? list[0].pid : null,
        comm: list.length === 1 ? sanitiseLabel(list[0].comm) : "",
        kind: kind
    };
}

// ---------------------------------------------------------------------------
// Approval types

// Most specific first. An episode or merged group reports the most specific
// kind seen from the detector, the log or the requesters.
var KINDS = ["ssh", "op-cli", "environment", "unlock", "unknown"];

function kindRank(kind) {
    if (kind === "ssh" || kind === "op-cli" || kind === "environment") return 0;
    if (kind === "unlock") return 1;
    return 2;
}

// Keeps the first of two equally specific kinds.
function mergeKind(current, next) {
    if (KINDS.indexOf(next) < 0) return current;
    if (KINDS.indexOf(current) < 0) return next;
    return kindRank(next) < kindRank(current) ? next : current;
}

// ---------------------------------------------------------------------------
// Outcome rule

// Facts recorded when an episode closes:
//   reconciled  already open when the watcher started (unknown age)
//   lifetimeMs  open to close
//   signal      a not-given log signature in its lifetime ("timeout" or
//               "cancel"), else null
//   covered     input observations were valid for the whole lifetime
//   inputSeen   raw input (before the synthetic-activity filter) after it
//               opened and at or before it closed
// Not given when any of: a timeout or cancellation was logged, it lasted at
// least expired_min_seconds, or input was observed throughout and none came.
function classifyEpisode(facts, config) {
    if (facts.reconciled) return { outcome: "reconciled", reason: "already open at start" };
    if (facts.signal) return { outcome: "not_given", reason: "1Password logged a " + (facts.signal === "timeout" ? "timeout" : "cancellation") };
    if (facts.lifetimeMs >= config.watcher.expired_min_seconds * 1000)
        return { outcome: "not_given", reason: "open for " + Math.floor(facts.lifetimeMs / 1000) + " s" };
    if (facts.covered && !facts.inputSeen) return { outcome: "not_given", reason: "no input while open" };
    if (!facts.covered) return { outcome: "answered", reason: "input not observed throughout" };
    return { outcome: "answered", reason: "input while open" };
}

// Overlapping episodes are one group: not given if any member that is not
// reconciled was not given; reconciled only if every member was.
function classifyGroup(factsList, config) {
    var answered = null;
    for (var i = 0; i < factsList.length; i++) {
        var r = classifyEpisode(factsList[i], config);
        if (r.outcome === "not_given") return r;
        if (r.outcome === "answered" && !answered) answered = r;
    }
    return answered || { outcome: "reconciled", reason: "already open at start" };
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

// obs: {sessionUp, lock: "locked"|"unlocked"|"unknown", activity (from
// activityReduce), nowMs}. Until real input has been seen since the monitor
// was created, the time since creation is only a lower bound on idleness: it
// can show idle or away, never present.
function derivePresence(obs, config) {
    if (!obs.sessionUp) return "unknown";
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
// (epoch seconds, rounded up) only while activity is held. engine: the hash
// of the shared code this watcher runs (contentHash), for comparing machines.
function presenceDocument(machine, state, nowMs, lastPresentAt, pendingUntilMs, engine) {
    var doc = {
        machine: machine,
        state: state,
        updated_at: isoWithOffset(new Date(nowMs)),
        updated_epoch: Math.floor(nowMs / 1000),
        last_present_at: lastPresentAt === null || lastPresentAt === undefined ? null : lastPresentAt
    };
    if (pendingUntilMs !== null && pendingUntilMs !== undefined)
        doc.activity_pending_until = Math.ceil(pendingUntilMs / 1000);
    if (engine) doc.engine = engine;
    return doc;
}

// ---------------------------------------------------------------------------
// Fallback (decision 10, D2, D10)

function stateAlerts(state, config) {
    return state !== "present" && config.alerts.presence_states.indexOf(state) >= 0;
}

// When a group closes: start the grace timer only for a group that was not
// given while Rod is not present.
function graceEligible(group, classification, state, config) {
    if (classification.outcome !== "not_given") return { eligible: false, reason: classification.outcome };
    if (!config.watcher.fallback) return { eligible: false, reason: "fallback disabled" };
    if (group.fallbackAttempted) return { eligible: false, reason: "already attempted" };
    if (state === "present") return { eligible: false, reason: "present when it closed" };
    if (!stateAlerts(state, config)) return { eligible: false, reason: "presence " + state + " excluded by alerts.presence_states" };
    return { eligible: true, reason: "not given (" + classification.reason + ") while " + state };
}

// When the grace timer fires, against the config in force then: the group
// must still classify as not given (its recorded facts against the current
// expired_min_seconds), Rod must still not be present and must not have been
// present at any point since it closed (any return cancels, even if he left
// again). The shared claim (D10) is taken after this.
function fallbackDecision(group, state, lastPresentAt, config) {
    var classification = classifyGroup(group.facts, config);
    if (classification.outcome !== "not_given") return { send: false, reason: classification.outcome + " under the current config" };
    if (group.fallbackAttempted) return { send: false, reason: "already attempted" };
    if (!config.watcher.fallback) return { send: false, reason: "fallback disabled" };
    if (state === "present") return { send: false, reason: "present" };
    if (!stateAlerts(state, config)) return { send: false, reason: "presence " + state + " excluded by alerts.presence_states" };
    if (lastPresentAt !== null && lastPresentAt !== undefined && lastPresentAt >= group.expiredAt)
        return { send: false, reason: "present since it closed" };
    return { send: true, reason: "still not present" };
}

// ---------------------------------------------------------------------------
// 1Password log signatures

// A line looks like
//   INFO  2026-10-08T02:00:45.331+00:00 runtime-worker(ThreadId(8)) [1P:ssh/op-ssh-agent/src/lib.rs:649] Session was not authorized
//   INFO  2026-09-30T01:06:23.317+00:00 ThreadId(2324) [swift] ProcessValidation.swift:550: validateProcess...(client:) Will validate remote process
// Signatures match the source path and the message, never line numbers,
// which change between releases.
//   signal  "timeout" or "cancel" (not given), or "unlock" (an unlock was
//           requested; qualifies a system authentication window)
//   kind    approval type hint
var LOG_SOURCES = [
    { source: "op-ssh-agent/", messages: [
        { text: "ssh authorization prompt timed out", signal: "timeout", kind: "ssh" },
        { text: "Session was not authorized", signal: "cancel", kind: "ssh" },
        { text: "Notifying user through tray icon that they have a background prompt waiting", kind: "ssh" }
    ], known: ["failed to find NSApplication related to pid", "failed to receive agent request", "Biometry is ready"] },
    { source: "components/ssh_agent.rs", messages: [
        { text: "received error from SSH auth prompt", signal: "cancel", kind: "ssh" }
    ], known: [] },
    { source: "backend/lock.rs", messages: [
        { text: "Locked. Reason: Automatic(DeviceWentToSleep)", signal: "cancel" }
    ], known: ["Lock state changed", "Locked. Reason:", "Unlocked"] },
    { source: "op-unlock/", messages: [
        { text: "System unlock proceeding", signal: "unlock", kind: "unlock" }
    ], known: [] },
    { source: "op-system-auth/", messages: [
        { text: "AppCancel invoked by a timed-out prompt", signal: "timeout" }
    ], known: ["Starting macOS lid/clamshell watcher"] },
    { source: "op-automated-unlock/", messages: [
        { text: "Failed to authorize using system biometry", kind: "unlock" }
    ], known: [] },
    { source: "developer/environment/", messages: [
        { text: "Developer Environment file mount auth was denied by the user", kind: "environment" }
    ], known: [] },
    { source: "ProcessValidation.swift", messages: [
        { text: "Will validate remote process", kind: "op-cli" }
    ], known: ["verifySignatureOfSelfMatchesSignature"] }
];

// {source, message, atMs} from one log line, or null. atMs is the line's
// own timestamp (epoch ms), or null when it has none: lines reach the
// watcher up to a few hundred milliseconds after they were written, so the
// timestamp, not the arrival, places a line within an episode.
function parseLogLine(line) {
    var text = String(line === undefined || line === null ? "" : line);
    var ts = /^\S+\s+(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d))\s/.exec(text);
    var atMs = ts ? Date.parse(ts[1]) : NaN;
    atMs = isFinite(atMs) ? atMs : null;
    var m = /\[1P:([^\]]+?):\d+\] ?(.*)$/.exec(text);
    if (m) return { source: m[1], message: m[2], atMs: atMs };
    m = /\[swift\] ([^ :]+):\d+: ?(.*)$/.exec(text);
    if (m) return { source: m[1], message: m[2], atMs: atMs };
    return null;
}

// {source, signal, kind, unrecognised, atMs} for a line from a signature
// source: source is the table's source (never the line), signal and kind
// null when the message matches nothing; unrecognised is true for a message
// that is neither a signature nor known noise. null for every other line.
function matchLogLine(line) {
    var parsed = parseLogLine(line);
    if (!parsed) return null;
    for (var i = 0; i < LOG_SOURCES.length; i++) {
        var entry = LOG_SOURCES[i];
        if (parsed.source.indexOf(entry.source) < 0) continue;
        for (var j = 0; j < entry.messages.length; j++) {
            if (parsed.message.indexOf(entry.messages[j].text) >= 0)
                return { source: entry.source, signal: entry.messages[j].signal || null,
                         kind: entry.messages[j].kind || null, unrecognised: false, atMs: parsed.atMs };
        }
        var known = false;
        for (var k = 0; k < entry.known.length; k++)
            if (parsed.message.indexOf(entry.known[k]) >= 0) known = true;
        return { source: entry.source, signal: null, kind: null, unrecognised: !known, atMs: parsed.atMs };
    }
    return null;
}

// ---------------------------------------------------------------------------
// macOS approval windows (from CGWindowListCopyWindowInfo, no titles)

// Approval windows are new 1Password windows at layer 101, 400 points wide
// once shown. Quick Access is also at layer 101 but is created once and
// shown and hidden (550 wide); the main window and Settings are at layer 0.
// The system Touch ID dialog (coreautha, layer 1000) counts only when
// 1Password logged an unlock request at most UNLOCK_LINE_MS before it
// opened (discovery: 84 to 400 ms).
var MAC_APPROVAL_OWNER = "1Password";
var MAC_APPROVAL_LAYER = 101;
var MAC_APPROVAL_WIDTH = 400;
var MAC_SYSTEM_AUTH_OWNER = "coreautha";
var MAC_SYSTEM_AUTH_LAYER = 1000;
var UNLOCK_LINE_MS = 1000;

// What a window can become once it appears: "approval", "system-auth" or
// null. w: {owner, layer, width, onScreen}.
function macCandidateSource(w) {
    if (!w) return null;
    if (w.owner === MAC_APPROVAL_OWNER && w.layer === MAC_APPROVAL_LAYER) return "approval";
    if (w.owner === MAC_SYSTEM_AUTH_OWNER && w.layer === MAC_SYSTEM_AUTH_LAYER) return "system-auth";
    return null;
}

// The confirmation check, confirm_seconds after the window appeared. w is
// the window now, or null if it is gone.
function macConfirm(source, w) {
    if (!w) return { confirmed: false, reason: "closed before confirmation" };
    if (!w.onScreen) return { confirmed: false, reason: "not on screen" };
    if (source === "approval") {
        if (w.layer !== MAC_APPROVAL_LAYER) return { confirmed: false, reason: "layer differs" };
        if (Math.round(w.width) !== MAC_APPROVAL_WIDTH) return { confirmed: false, reason: "width differs" };
        return { confirmed: true, reason: "approval window" };
    }
    if (source === "system-auth") return { confirmed: true, reason: "system authentication window" };
    return { confirmed: false, reason: "unknown source" };
}

// ---------------------------------------------------------------------------
// Shared code identity

// FNV-1a over the UTF-16 code units, as 8 hex digits: the same text gives
// the same hash in every JavaScript engine.
function contentHash(text) {
    var h = 0x811c9dc5;
    var s = String(text);
    for (var i = 0; i < s.length; i++) {
        h ^= s.charCodeAt(i);
        h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
    }
    return ("0000000" + h.toString(16)).slice(-8);
}

var POLICY = {
    WINDOW_CLASS: WINDOW_CLASS,
    WINDOW_TITLE: WINDOW_TITLE,
    KINDS: KINDS,
    CLOSE_WINDOW_MS: CLOSE_WINDOW_MS,
    CONFIRM_MS: CONFIRM_MS,
    RESUME_GAP_MS: RESUME_GAP_MS,
    UNLOCK_LINE_MS: UNLOCK_LINE_MS,
    defaults: defaults,
    normaliseConfig: normaliseConfig,
    sanitiseLabel: sanitiseLabel,
    addressKey: addressKey,
    parseWindowEvent: parseWindowEvent,
    isApprovalClass: isApprovalClass,
    isApprovalTitle: isApprovalTitle,
    confirmCandidate: confirmCandidate,
    requesterOutcome: requesterOutcome,
    kindRank: kindRank,
    mergeKind: mergeKind,
    classifyEpisode: classifyEpisode,
    classifyGroup: classifyGroup,
    activityReset: activityReset,
    activityPendingUntil: activityPendingUntil,
    activityReduce: activityReduce,
    derivePresence: derivePresence,
    nextLastPresentAt: nextLastPresentAt,
    restoredLastPresentAt: restoredLastPresentAt,
    isoWithOffset: isoWithOffset,
    presenceDocument: presenceDocument,
    stateAlerts: stateAlerts,
    graceEligible: graceEligible,
    fallbackDecision: fallbackDecision,
    parseLogLine: parseLogLine,
    matchLogLine: matchLogLine,
    macCandidateSource: macCandidateSource,
    macConfirm: macConfirm,
    contentHash: contentHash
};

if (typeof module !== "undefined") module.exports = POLICY;
