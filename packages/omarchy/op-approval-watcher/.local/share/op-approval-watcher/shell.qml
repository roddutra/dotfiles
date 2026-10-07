// 1Password approval watcher: a standalone Quickshell instance with no
// windows, run by op-approval-watcher.service. It
//   1. publishes Rod's presence to ${XDG_RUNTIME_DIR}/op-approval/presence.json
//      for the op-approval-blocked skill and the shared alert claim, and
//   2. sends one fallback alert when a 1Password approval prompt expired while
//      Rod was away and he has not come back within the grace period. The agent
//      that hit the prompt normally alerts first through the skill; the shared
//      claim then suppresses this one.
// It never alerts while a prompt is pending. Decision rules live in Policy.js.
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import "Policy.js" as Policy

ShellRoot {
    id: root

    // A changed file on disk must not reload the watcher and drop its state.
    settings.watchFiles: false

    readonly property string home: Quickshell.env("HOME") || ""
    readonly property string runtimeDir: Quickshell.env("XDG_RUNTIME_DIR") || ""
    readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || (home + "/.config")
    readonly property string libDir: Quickshell.env("OP_APPROVAL_LIB") || (home + "/.agents/lib/op-approval")
    readonly property string feedDir: runtimeDir + "/op-approval"
    readonly property string requestersPath: Quickshell.shellPath("requesters")
    readonly property string runId: Math.random().toString(36).slice(2, 6)

    property var cfg: Policy.defaults()
    property string configText: "\u0000unloaded"
    property string hostname: ""

    // Observations (see Policy.derivePresence)
    property bool hyprlandUp: true
    property string lockState: "unknown"
    property var activity: Policy.activityReset(Date.now(), null)
    property int monitorGeneration: 0
    property var idleMonitor: null
    property string presenceState: "unknown"
    property var lastPresentAt: null
    property var publishedPendingUntil: null

    // Episodes, keyed by a per-window generation so a reused address can never
    // satisfy a check meant for an earlier window.
    property int generation: 0
    property int episodeSeq: 0
    property var candidates: ({})
    property var addressGen: ({})
    property var graces: ({})
    property var processes: []
    property bool lockPollRunning: false
    property bool healthRunning: false

    function log(message) {
        console.info("op-approval-watcher: " + message);
    }

    function warn(message) {
        console.warn("op-approval-watcher: " + message);
    }

    // -----------------------------------------------------------------------
    // Processes: non-blocking, with a deadline enforced by the 1 s tick.

    Component {
        id: processComponent
        Process {
            id: proc
            property var callback: null
            property double deadline: 0
            property bool exitSeen: false
            property bool streamSeen: false
            property bool done: false
            property int code: -1
            stdout: StdioCollector {
                id: collector
                onStreamFinished: {
                    proc.streamSeen = true;
                    proc.finish();
                }
            }
            onExited: (exitCode, exitStatus) => {
                proc.code = exitStatus === 0 ? exitCode : -1;
                proc.exitSeen = true;
                proc.finish();
            }
            function finish() {
                if (done || !exitSeen || !streamSeen)
                    return;
                complete(code, collector.text);
            }
            function complete(exitCode, text) {
                if (done)
                    return;
                done = true;
                const cb = callback;
                callback = null;
                root.forgetProcess(proc);
                Qt.callLater(() => proc.destroy());
                if (cb)
                    cb(exitCode, text || "");
            }
        }
    }

    function run(command, timeoutMs, callback) {
        const proc = processComponent.createObject(root, {
            command: command,
            callback: callback,
            deadline: Date.now() + timeoutMs
        });
        processes.push(proc);
        proc.running = true;
        return proc;
    }

    function forgetProcess(proc) {
        const i = processes.indexOf(proc);
        if (i >= 0)
            processes.splice(i, 1);
    }

    function expireProcesses(nowMs) {
        processes.slice().forEach(proc => {
            if (proc.done || nowMs < proc.deadline)
                return;
            if (proc.running)
                proc.signal(9);
            proc.complete(-1, "");
        });
    }

    // One-shot timers (confirmation delay, grace period).
    Component {
        id: timerComponent
        Timer {
            id: oneShot
            property var action: null
            repeat: false
            onTriggered: {
                const a = action;
                action = null;
                Qt.callLater(() => oneShot.destroy());
                if (a)
                    a();
            }
        }
    }

    function after(ms, action) {
        const t = timerComponent.createObject(root, { interval: Math.max(1, Math.round(ms)), action: action });
        t.start();
        return t;
    }

    function cancelTimer(t) {
        if (!t || !t.action)
            return;
        t.action = null;
        t.stop();
        Qt.callLater(() => t.destroy());
    }

    // -----------------------------------------------------------------------
    // Configuration: ${XDG_CONFIG_HOME:-$HOME/.config}/op-approval/config.json,
    // re-read on change and every 30 s (an editor that replaces the file, or a
    // file created after start, is not always seen by the watch).

    FileView {
        id: configFile
        path: root.configHome + "/op-approval/config.json"
        watchChanges: true
        blockLoading: true
        printErrors: false
        // Wait for a writer to finish before reading.
        onFileChanged: configSettle.restart()
        onLoaded: root.applyConfigText(text())
        onLoadFailed: root.applyConfigText(null)
    }

    Timer {
        id: configSettle
        interval: 500
        onTriggered: configFile.reload()
    }

    function applyConfigText(text) {
        const key = text === null ? "\u0000missing" : text;
        if (key === configText)
            return;
        configText = key;
        let raw;
        let parseError = false;
        if (text !== null && text.trim() !== "") {
            try {
                raw = JSON.parse(text);
            } catch (e) {
                parseError = true;
            }
        }
        const result = Policy.normaliseConfig(raw, parseError);
        result.warnings.forEach(w => warn(w));
        cfg = result.config;
        const w = cfg.watcher;
        log("config " + (text === null ? "missing, using the defaults" : "loaded") + ": present " + cfg.presence.present_seconds + " s, away " + cfg.presence.away_seconds + " s, fallback " + w.fallback + ", grace " + w.fallback_grace_seconds + " s, expired after " + w.expired_min_seconds + " s, confirm after " + w.confirm_seconds + " s, alert states " + cfg.alerts.presence_states.join("/"));
        recompute();
    }

    FileView {
        id: hostnameFile
        path: "/proc/sys/kernel/hostname"
        blockLoading: true
        printErrors: false
    }

    function machineLabel() {
        const configured = cfg.machine ? Policy.sanitiseLabel(cfg.machine) : "";
        return configured || Policy.sanitiseLabel(hostname) || "unknown";
    }

    // -----------------------------------------------------------------------
    // Idle observation: one 5 s monitor (ext-idle-notify v2 input idleness,
    // inhibitors ignored). Idle and away come from the wall clock since the
    // last real input; activity right next to a window or layer close is held
    // until it proves real (Policy.activityReduce). The monitor is re-created
    // on start and resume, and observations stay invalid until it reports
    // idle once.

    Component {
        id: monitorComponent
        IdleMonitor {
            respectInhibitors: false
            timeout: 5
        }
    }

    function createMonitors(reason) {
        const old = idleMonitor;
        monitorGeneration += 1;
        const gen = monitorGeneration;
        activity = Policy.activityReset(Date.now(), activity.lastCloseMs);
        const m = monitorComponent.createObject(root);
        m.isIdleChanged.connect(() => root.onIdleChanged(gen, m));
        idleMonitor = m;
        if (old)
            old.destroy();
        log("idle monitor (re)created (" + reason + "); observations invalid until 5 s of idleness");
        recompute();
    }

    function onIdleChanged(gen, monitor) {
        if (gen !== monitorGeneration)
            return;
        const now = Date.now();
        applyActivity({ type: monitor.isIdle ? "idle" : "active", atMs: now });
        if (!monitor.isIdle) {
            // Resolve the pending activity on time rather than on the 1 s tick.
            after(Policy.CLOSE_WINDOW_MS + 20, () => applyActivity({ type: "tick", atMs: Date.now() }));
            after(Policy.CONFIRM_MS + 20, () => applyActivity({ type: "tick", atMs: Date.now() }));
        }
        pollLock();
    }

    function applyActivity(event) {
        const wasValid = activity.valid;
        const result = Policy.activityReduce(activity, event);
        activity = result.state;
        if (result.note === "resume") {
            // Qt timers stop during suspend; the wall clock does not. The
            // reducer has already dropped anything held before the gap.
            log("wall clock jumped (resume or clock change)");
            cancelGraces("resume");
            createMonitors("resume");
            pollLock();
            return;
        }
        if (!wasValid && activity.valid)
            log("observations valid");
        if (result.note === "suspect")
            log("activity within " + Policy.CLOSE_WINDOW_MS + " ms of a window or layer close: held until confirmed");
        else if (result.note === "discarded")
            log("held activity discarded as synthetic (idle again within " + Policy.CONFIRM_MS / 1000 + " s)");
        else if (result.note === "confirmed")
            log("held activity confirmed as real input");
        recompute();
    }

    // -----------------------------------------------------------------------
    // Lock state from the compositor's ext-session-lock (D4):
    // omarchy-hyprland-session-locked exits 0 locked, 1 unlocked, 2 undetermined.

    function anyPending() {
        return Object.keys(candidates).length > 0 || Object.keys(graces).length > 0;
    }

    Timer {
        id: lockTimer
        interval: 10000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.pollLock()
    }

    // Every 2 s while a candidate, episode or grace period is pending.
    function updateLockInterval() {
        const wanted = anyPending() ? 2000 : 10000;
        if (lockTimer.interval !== wanted)
            lockTimer.interval = wanted;
    }

    function pollLock() {
        if (lockPollRunning)
            return;
        lockPollRunning = true;
        run(["omarchy-hyprland-session-locked"], 5000, code => {
            lockPollRunning = false;
            const next = code === 0 ? "locked" : code === 1 ? "unlocked" : "unknown";
            if (next !== lockState) {
                log("lock state " + lockState + " -> " + next);
                lockState = next;
            }
            recompute();
        });
    }

    // -----------------------------------------------------------------------
    // Presence feed

    FileView {
        id: feedFile
        path: root.feedDir + "/presence.json"
        atomicWrites: true
        blockLoading: true
        printErrors: false
        onSaveFailed: error => {
            root.warn("cannot write the presence feed (error " + error + "); recreating its directory");
            root.run(["mkdir", "-p", "-m", "700", root.feedDir], 5000, () => {});
        }
    }

    function recompute() {
        const now = Date.now();
        const previous = presenceState;
        const state = Policy.derivePresence({
            hyprlandUp: hyprlandUp,
            lock: lockState,
            activity: activity,
            nowMs: now
        }, cfg);
        lastPresentAt = Policy.nextLastPresentAt(previous, state, lastPresentAt, Math.floor(now / 1000));
        presenceState = state;
        const pendingUntil = Policy.activityPendingUntil(activity);
        if (state !== previous) {
            log("presence " + previous + " -> " + state);
            writeFeed(now);
        } else if (pendingUntil !== publishedPendingUntil) {
            // Readers wait while activity is held; tell them at once.
            writeFeed(now);
        }
    }

    function writeFeed(nowMs) {
        publishedPendingUntil = Policy.activityPendingUntil(activity);
        const doc = Policy.presenceDocument(machineLabel(), presenceState, nowMs, lastPresentAt, publishedPendingUntil);
        feedFile.setText(JSON.stringify(doc) + "\n");
    }

    Timer {
        interval: 10000
        running: true
        repeat: true
        onTriggered: {
            root.recompute();
            root.writeFeed(Date.now());
        }
    }

    // -----------------------------------------------------------------------
    // Housekeeping tick: process deadlines, thresholds and resume detection.

    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: {
            const now = Date.now();
            root.expireProcesses(now);
            root.updateLockInterval();
            // Also moves presence across the idle and away thresholds, and
            // detects a resume (Policy.activityReduce).
            root.applyActivity({ type: "tick", atMs: now });
        }
    }

    Timer {
        interval: 30000
        running: true
        repeat: true
        onTriggered: configFile.reload()
    }

    // -----------------------------------------------------------------------
    // Hyprland health: on failure, give up so systemd restarts the watcher
    // against the live Hyprland instance.

    Timer {
        interval: 10000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.checkHealth()
    }

    function checkHealth() {
        if (healthRunning)
            return;
        healthRunning = true;
        run(["hyprctl", "version", "-j"], 5000, (code, text) => {
            healthRunning = false;
            let ok = code === 0;
            if (ok) {
                try {
                    JSON.parse(text);
                } catch (e) {
                    ok = false;
                }
            }
            // hyprctl exits 0 with no output when the socket closes unanswered.
            if (!ok)
                fail("Hyprland is not answering (hyprctl version exit " + code + (code === 0 ? ", no valid reply" : "") + ")");
        });
    }

    function fail(reason) {
        warn(reason + "; clearing episodes and exiting");
        cancelGraces("Hyprland lost");
        candidates = ({});
        addressGen = ({});
        hyprlandUp = false;
        activity = Policy.activityReset(Date.now(), null);
        recompute();
        writeFeed(Date.now());
        Qt.exit(1);
    }

    // -----------------------------------------------------------------------
    // Episodes (D2): a 1Password window whose title is still exactly
    // "1Password" confirm_seconds after it opened, with a requester (D3).

    Connections {
        target: Hyprland
        function onRawEvent(event) {
            if (event.name === "closewindow" || event.name === "closelayer")
                root.applyActivity({ type: "close", atMs: Date.now() });
            const e = Policy.parseWindowEvent(event.name, event.data);
            if (!e)
                return;
            if (e.type === "open")
                root.onWindowOpen(e);
            else if (e.type === "title")
                root.onWindowTitle(e);
            else if (e.type === "close")
                root.onWindowClose(e);
        }
    }

    // Every window of the 1Password class is a candidate; its title is judged
    // at the delayed check, so a window that gains the title late still counts.
    function onWindowOpen(e) {
        if (!Policy.isApprovalClass(e.windowClass))
            return;
        addCandidate(e.address, Date.now(), false);
    }

    // Once the check has started, any change away from "1Password"
    // disqualifies the window.
    function onWindowTitle(e) {
        const c = candidates[addressGen[e.address]];
        if (c && !c.closed && c.checkStarted && !Policy.isApprovalTitle(e.title) && !c.titleChanged) {
            c.titleChanged = true;
            if (c.episodeId)
                log("episode " + c.episodeId + ": window title changed");
        }
    }

    function addCandidate(address, openedAtMs, reconciled) {
        generation += 1;
        const c = {
            gen: generation,
            address: address,
            openedAtMs: openedAtMs,
            reconciled: reconciled,
            checkStarted: false,
            titleChanged: false,
            closed: false,
            episodeId: null,
            requesterCount: 0,
            identity: "{}",
            timer: null
        };
        candidates[c.gen] = c;
        addressGen[address] = c.gen;
        updateLockInterval();
        c.timer = after(cfg.watcher.confirm_seconds * 1000, () => {
            c.timer = null;
            confirm(c);
        });
    }

    function current(c) {
        return !c.closed && candidates[c.gen] === c && addressGen[c.address] === c.gen;
    }

    function drop(c, reason, titleMatched) {
        log("1Password window (class matched, title matched: " + titleMatched + (c.reconciled ? ", reconciled" : "") + ") is not an approval: " + reason);
        delete candidates[c.gen];
        if (addressGen[c.address] === c.gen)
            delete addressGen[c.address];
    }

    function confirm(c) {
        if (!current(c))
            return;
        c.checkStarted = true;
        run(["hyprctl", "clients", "-j"], 5000, (code, text) => {
            if (!current(c))
                return;
            let clients = null;
            if (code === 0) {
                try {
                    clients = JSON.parse(text);
                } catch (err) {
                    clients = null;
                }
            }
            const check = Policy.confirmCandidate(c, clients);
            if (!check.confirmed) {
                drop(c, check.reason, check.reason === "title differs" ? false : check.reason === "title changed" ? true : "unknown");
                return;
            }
            findRequesters(c);
        });
    }

    function findRequesters(c) {
        const args = c.reconciled ? ["--reconciled"] : ["--opened-at", (c.openedAtMs / 1000).toFixed(3)];
        run([requestersPath].concat(args), 10000, (code, text) => {
            if (!current(c))
                return;
            if (c.titleChanged) {
                drop(c, "title changed during the requester check", true);
                return;
            }
            let result = null;
            if (code === 0) {
                try {
                    result = JSON.parse(text);
                } catch (err) {
                    result = null;
                }
            }
            if (!result) {
                drop(c, "requester check failed (exit " + code + ")", true);
                return;
            }
            const outcome = Policy.requesterOutcome(result);
            if (!outcome.episode) {
                drop(c, "no requester candidate", true);
                return;
            }
            startEpisode(c, outcome, result);
        });
    }

    function startEpisode(c, outcome, result) {
        episodeSeq += 1;
        c.episodeId = runId + "-" + episodeSeq;
        c.requesterCount = outcome.count;
        const sources = {};
        result.candidates.forEach(r => sources[r.source] = (sources[r.source] || 0) + 1);
        log("episode " + c.episodeId + " started" + (c.reconciled ? " (reconciled, never fallback-eligible)" : "") + ": " + outcome.count + " requester candidate(s) " + JSON.stringify(sources));
        if (outcome.pid === null) {
            log("episode " + c.episodeId + ": several requesters, the fallback names the machine only");
            return;
        }
        // Identify now: the requester may exit before the fallback is due.
        run([libDir + "/locate", "--pid", String(outcome.pid)], 15000, (code, text) => {
            let identity = null;
            if (code === 0) {
                try {
                    identity = JSON.parse(text);
                } catch (err) {
                    identity = null;
                }
            }
            if (identity && typeof identity === "object" && !Array.isArray(identity)) {
                c.identity = JSON.stringify(identity);
                log("episode " + c.episodeId + ": requester identified");
            } else {
                log("episode " + c.episodeId + ": requester not identified (locate exit " + code + "), the fallback names the machine only");
            }
        });
    }

    function onWindowClose(e) {
        const gen = addressGen[e.address];
        if (gen === undefined)
            return;
        delete addressGen[e.address];
        const c = candidates[gen];
        if (!c)
            return;
        delete candidates[gen];
        c.closed = true;
        cancelTimer(c.timer);
        c.timer = null;
        const closedAtMs = Date.now();
        c.closedAtMs = closedAtMs;
        if (!c.episodeId) {
            log("1Password window (class matched" + (c.reconciled ? ", reconciled" : "") + ") closed before confirmation");
            return;
        }
        const lifetime = ((closedAtMs - c.openedAtMs) / 1000).toFixed(1);
        const classification = Policy.classifyEnd(c, closedAtMs, cfg);
        log("episode " + c.episodeId + " ended: " + classification + (c.reconciled ? "" : " after " + lifetime + " s"));
        const grace = Policy.graceEligible(c, classification, presenceState, cfg);
        if (!grace.eligible) {
            if (classification === "expired")
                log("episode " + c.episodeId + ": no fallback (" + grace.reason + ")");
            return;
        }
        c.expiredAt = Math.floor(closedAtMs / 1000);
        log("episode " + c.episodeId + ": " + grace.reason + ", fallback in " + cfg.watcher.fallback_grace_seconds + " s unless Rod returns");
        graces[c.gen] = c;
        c.timer = after(cfg.watcher.fallback_grace_seconds * 1000, () => {
            c.timer = null;
            delete graces[c.gen];
            fireFallback(c);
        });
    }

    function cancelGraces(reason) {
        Object.keys(graces).forEach(gen => {
            const c = graces[gen];
            cancelTimer(c.timer);
            c.timer = null;
            log("episode " + c.episodeId + ": fallback cancelled (" + reason + ")");
        });
        graces = ({});
    }

    function fireFallback(c) {
        if (activity.pending) {
            // Wait until held activity is confirmed or discarded.
            log("episode " + c.episodeId + ": fallback waits for held activity to resolve");
            graces[c.gen] = c;
            c.timer = after(Policy.CONFIRM_MS + 500, () => {
                c.timer = null;
                delete graces[c.gen];
                fireFallback(c);
            });
            return;
        }
        recompute();
        const decision = Policy.fallbackDecision(c, presenceState, lastPresentAt, cfg);
        if (!decision.send) {
            log("episode " + c.episodeId + ": no fallback (" + decision.reason + ")");
            return;
        }
        // At most one attempt per episode, whatever happens next. No retry.
        c.fallbackAttempted = true;
        run([libDir + "/claim", "take", "--source", "watcher", "--expired-at", String(c.expiredAt), "--require-away"], 15000, (code, text) => {
            const answer = (text || "").trim().split("\n")[0];
            if (code !== 0) {
                log("episode " + c.episodeId + ": claim refused (exit " + code + (answer ? ": " + answer : "") + "), no fallback");
                return;
            }
            log("episode " + c.episodeId + ": claim granted, publishing the fallback");
            run([libDir + "/publish", "--template", "fallback", "--identity", c.identity], 20000, (pcode, ptext) => {
                let out = null;
                try {
                    out = JSON.parse((ptext || "").trim());
                } catch (err) {
                    out = null;
                }
                const result = out && out.result ? out.result : "failed";
                const detail = out ? (out.reason || (out.http_status !== undefined ? "HTTP " + out.http_status + (out.curl_exit ? ", curl exit " + out.curl_exit : "") : "")) : "no output";
                log("episode " + c.episodeId + ": fallback " + result + " (exit " + pcode + (detail ? ", " + detail : "") + ")");
            });
        });
    }

    // Approval windows already open at start: candidates of unknown age that
    // go through the same re-check and requester check, never fallback-eligible.
    function reconcile() {
        run(["hyprctl", "clients", "-j"], 5000, (code, text) => {
            let clients = [];
            if (code === 0) {
                try {
                    clients = JSON.parse(text);
                } catch (err) {
                    clients = [];
                }
            }
            if (!Array.isArray(clients))
                clients = [];
            let found = 0;
            clients.forEach(client => {
                if (!client || !Policy.isApprovalClass(client["class"]) || !Policy.isApprovalTitle(client.title))
                    return;
                const address = Policy.addressKey(client.address);
                if (!address || addressGen[address] !== undefined)
                    return;
                found += 1;
                addCandidate(address, Date.now(), true);
            });
            log("reconciled " + found + " open 1Password window(s) titled 1Password" + (code === 0 ? "" : " (hyprctl clients exit " + code + ")"));
        });
    }

    Component.onCompleted: {
        if (!runtimeDir) {
            console.error("op-approval-watcher: XDG_RUNTIME_DIR is not set");
            Qt.exit(1);
            return;
        }
        hostname = (hostnameFile.text() || "").trim();
        try {
            lastPresentAt = Policy.restoredLastPresentAt(JSON.parse(feedFile.text()), Math.floor(Date.now() / 1000));
        } catch (e) {
            lastPresentAt = null;
        }
        if (!configFile.loaded)
            applyConfigText(configFile.text() || null);
        log("started (run " + runId + "), last present " + (lastPresentAt === null ? "unknown" : Policy.isoWithOffset(new Date(lastPresentAt * 1000))));
        createMonitors("start");
        writeFeed(Date.now());
        reconcile();
    }
}
