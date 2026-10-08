// 1Password approval watcher: a standalone Quickshell instance with no
// windows, run by op-approval-watcher.service.
//
// This is the Omarchy host of the shared engine (Engine.js and Policy.js,
// installed next to this file from packages/common/op-approval-watcher). It
// turns Hyprland, idle, lock and 1Password log signals into engine events
// and carries out the effects the engine returns: see Engine.js for the
// contract. It decides nothing itself, so a behaviour change made in the
// shared files applies here and on macOS alike.
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import "Policy.js" as PolicyJs
import "Engine.js" as EngineJs

ShellRoot {
    id: root

    // A changed file on disk must not reload the watcher and drop its state;
    // the engine asks for the shared files and restarts on new code.
    settings.watchFiles: false

    readonly property string home: Quickshell.env("HOME") || ""
    readonly property string runtimeDir: Quickshell.env("XDG_RUNTIME_DIR") || ""
    readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || (home + "/.config")
    readonly property string configPath: configHome + "/op-approval/config.json"
    readonly property string libDir: Quickshell.env("OP_APPROVAL_LIB") || (home + "/.agents/lib/op-approval")
    readonly property string feedDir: Quickshell.env("OP_APPROVAL_RUNTIME_DIR") || (runtimeDir + "/op-approval")
    readonly property string onePasswordLog: home + "/.config/1Password/logs/1Password_rCURRENT.log"
    readonly property string runId: Math.random().toString(36).slice(2, 6)

    readonly property var policy: PolicyJs.POLICY
    readonly property var engine: EngineJs.createEngine(PolicyJs.POLICY)
    property var engineState: engine.initial()
    property var queue: []
    property bool draining: false

    property int monitorGeneration: 0
    property var idleMonitor: null
    property var processes: []
    property var timers: ({})
    // 1Password windows reported to the engine, by address.
    property var windows: ({})

    function log(message) {
        console.info("op-approval-watcher: " + message);
    }

    function warn(message) {
        console.warn("op-approval-watcher: " + message);
    }

    // -----------------------------------------------------------------------
    // Engine: events are queued so an effect answered at once is handled
    // after the effects of the step that asked for it.

    function send(event) {
        if (event.atMs === undefined)
            event.atMs = Date.now();
        queue.push(event);
        if (draining)
            return;
        draining = true;
        while (queue.length > 0) {
            const next = queue.shift();
            let result;
            try {
                result = engine.step(engineState, next);
            } catch (e) {
                warn("engine error on a " + next.type + " event: " + e);
                continue;
            }
            engineState = result.state;
            result.effects.forEach(effect => apply(effect));
        }
        draining = false;
    }

    function apply(effect) {
        switch (effect.type) {
        case "log":
            if (effect.level === "warn")
                warn(effect.message);
            else
                log(effect.message);
            break;
        case "write_feed":
            feedFile.setText(JSON.stringify(effect.document) + "\n");
            break;
        case "run":
            runHelper(effect);
            break;
        case "observe":
            observe(effect);
            break;
        case "reset_input":
            createMonitor();
            break;
        case "set_timer":
            timers[effect.id] = after(effect.delayMs, () => {
                delete timers[effect.id];
                send({ type: "timer_fired", id: effect.id });
            });
            break;
        case "cancel_timer":
            cancelTimer(timers[effect.id]);
            delete timers[effect.id];
            break;
        case "exit":
            log("exiting (" + effect.code + ")");
            Qt.exit(effect.code);
            break;
        default:
            warn("unknown effect " + effect.type);
        }
    }

    function answer(id, result) {
        send({ type: "observed", id: id, result: result });
    }

    function parseJson(code, text) {
        if (code !== 0)
            return null;
        try {
            return JSON.parse(text);
        } catch (e) {
            return null;
        }
    }

    function observe(effect) {
        switch (effect.what) {
        case "candidate":
            confirmWindow(effect.id, effect.key);
            break;
        case "open_candidates":
            reconcile(effect.id);
            break;
        case "lock":
            // omarchy-hyprland-session-locked exits 0 locked, 1 unlocked,
            // 2 undetermined.
            run(["omarchy-hyprland-session-locked"], 5000, code => {
                answer(effect.id, { state: code === 0 ? "locked" : code === 1 ? "unlocked" : "unknown" });
            });
            break;
        case "session":
            run(["hyprctl", "version", "-j"], 5000, (code, text) => {
                // hyprctl exits 0 with no output when the socket closes unanswered.
                const ok = parseJson(code, text) !== null;
                answer(effect.id, ok ? { state: "up" } : { state: "lost", detail: "hyprctl version exit " + code + (code === 0 ? ", no valid reply" : "") });
            });
            break;
        case "config":
            run(["cat", "--", configPath], 5000, (code, text) => answer(effect.id, { text: code === 0 ? text : null }));
            break;
        case "code":
            readCode(code => answer(effect.id, code));
            break;
        default:
            answer(effect.id, null);
        }
    }

    function readCode(callback) {
        run(["cat", "--", Quickshell.shellPath("Policy.js")], 5000, (pcode, policyText) => {
            run(["cat", "--", Quickshell.shellPath("Engine.js")], 5000, (ecode, engineText) => {
                callback({ policy: pcode === 0 ? policyText : null, engine: ecode === 0 ? engineText : null });
            });
        });
    }

    function helperPath(name) {
        if (name === "requesters")
            return Quickshell.shellPath("requesters");
        if (name === "locate" || name === "claim" || name === "publish")
            return libDir + "/" + name;
        return null;
    }

    function runHelper(effect) {
        const path = helperPath(effect.helper);
        if (!path) {
            send({ type: "helper_done", id: effect.id, code: -1, output: "" });
            return;
        }
        run([path].concat(effect.args), effect.deadlineMs, (code, text) => {
            send({ type: "helper_done", id: effect.id, code: code, output: text });
        });
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

    // One-shot timers for the engine.
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

    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: {
            const now = Date.now();
            root.expireProcesses(now);
            root.send({ type: "tick", atMs: now });
        }
    }

    // -----------------------------------------------------------------------
    // Input: one 5 s monitor (ext-idle-notify v2 input idleness, inhibitors
    // ignored), re-created whenever the engine asks.

    Component {
        id: monitorComponent
        IdleMonitor {
            respectInhibitors: false
            timeout: 5
        }
    }

    function createMonitor() {
        const old = idleMonitor;
        monitorGeneration += 1;
        const gen = monitorGeneration;
        const m = monitorComponent.createObject(root);
        m.isIdleChanged.connect(() => {
            if (gen === root.monitorGeneration)
                root.send({ type: "input", state: m.isIdle ? "idle" : "active" });
        });
        idleMonitor = m;
        if (old)
            old.destroy();
    }

    // -----------------------------------------------------------------------
    // Files

    // Re-read on change, once a writer has finished; the engine also asks
    // every 30 s (an editor that replaces the file is not always seen).
    FileView {
        id: configFile
        path: root.configPath
        watchChanges: true
        blockLoading: true
        printErrors: false
        onFileChanged: configSettle.restart()
        onLoaded: root.send({ type: "config", text: text() })
        onLoadFailed: root.send({ type: "config", text: null })
    }

    Timer {
        id: configSettle
        interval: 500
        onTriggered: configFile.reload()
    }

    FileView {
        id: hostnameFile
        path: "/proc/sys/kernel/hostname"
        blockLoading: true
        printErrors: false
    }

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

    // 1Password's log, followed by name across rotation. Each new line goes
    // to the engine, which matches signatures and never logs the content.
    Process {
        id: logFollower
        command: ["tail", "-n", "0", "-F", root.onePasswordLog]
        stdout: SplitParser {
            onRead: line => root.send({ type: "log_line", line: line })
        }
        onExited: logRestart.restart()
    }

    Timer {
        id: logRestart
        interval: 10000
        onTriggered: logFollower.running = true
    }

    // -----------------------------------------------------------------------
    // Hyprland windows. Every window of the 1Password class is a candidate;
    // the engine asks for the confirmation check, which requires the exact
    // title "1Password" and no title change once the check has started (the
    // main window renames itself within about 0.3 s; Quick Access and
    // Settings have other titles).

    Connections {
        target: Hyprland
        function onRawEvent(event) {
            if (event.name === "closewindow" || event.name === "closelayer")
                root.send({ type: "surface_closed" });
            const e = root.policy.parseWindowEvent(event.name, event.data);
            if (!e)
                return;
            if (e.type === "open" && root.policy.isApprovalClass(e.windowClass)) {
                root.windows[e.address] = { address: e.address, closed: false, titleChanged: false, checkStarted: false };
                root.send({ type: "candidate_open", key: e.address, openedAtMs: Date.now(), reconciled: false, source: "approval" });
            } else if (e.type === "title") {
                const w = root.windows[e.address];
                if (w && w.checkStarted && !root.policy.isApprovalTitle(e.title))
                    w.titleChanged = true;
            } else if (e.type === "close" && root.windows[e.address]) {
                root.windows[e.address].closed = true;
                delete root.windows[e.address];
                root.send({ type: "candidate_closed", key: e.address, closedAtMs: Date.now() });
            }
        }
    }

    function confirmWindow(id, address) {
        const w = windows[address] || { address: address, closed: true, titleChanged: false };
        w.checkStarted = true;
        run(["hyprctl", "clients", "-j"], 5000, (code, text) => {
            const check = policy.confirmCandidate(w, parseJson(code, text));
            answer(id, { confirmed: check.confirmed, reason: check.reason });
        });
    }

    // Approval windows already open at start: unknown age, confirmed the
    // same way, never fallback-eligible.
    function reconcile(id) {
        run(["hyprctl", "clients", "-j"], 5000, (code, text) => {
            let clients = parseJson(code, text);
            if (!Array.isArray(clients))
                clients = [];
            const found = [];
            clients.forEach(client => {
                if (!client || !policy.isApprovalClass(client["class"]) || !policy.isApprovalTitle(client.title))
                    return;
                const address = policy.addressKey(client.address);
                if (!address || windows[address])
                    return;
                windows[address] = { address: address, closed: false, titleChanged: false, checkStarted: false };
                found.push({ key: address, source: "approval" });
            });
            answer(id, { candidates: found, detail: code === 0 ? "" : "hyprctl clients exit " + code });
        });
    }

    Component.onCompleted: {
        if (!runtimeDir && !Quickshell.env("OP_APPROVAL_RUNTIME_DIR")) {
            console.error("op-approval-watcher: XDG_RUNTIME_DIR is not set");
            Qt.exit(1);
            return;
        }
        const previousFeed = feedFile.text() || null;
        const config = configFile.text() || null;
        const hostname = (hostnameFile.text() || "").trim();
        readCode(code => {
            send({ type: "start", previousFeed: previousFeed, config: config, hostname: hostname, runId: runId, code: code });
            logFollower.running = true;
        });
    }
}
