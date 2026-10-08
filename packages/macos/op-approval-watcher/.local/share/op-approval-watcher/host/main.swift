// macOS host of the 1Password approval watcher, run by the LaunchAgent
// through ~/.local/bin/op-approval-watcher.
//
// It loads the shared Policy.js and Engine.js into JavaScriptCore, turns what
// it observes into engine events and carries out the effects the engine
// returns. It decides nothing itself: see Engine.js for the event and effect
// contract. Every signal comes from public APIs that need no privacy
// permission: the window list without titles, HID idle time, the session
// dictionary, workspace notifications and 1Password's log file.
import AppKit
import CoreGraphics
import Darwin
import Foundation
import JavaScriptCore
import os
import SystemConfiguration

let logger = Logger(subsystem: "op-approval-watcher", category: "watcher")

func info(_ message: String) {
    logger.info("\(message, privacy: .public)")
    FileHandle.standardError.write(Data(("op-approval-watcher: " + message + "\n").utf8))
}

func warn(_ message: String) {
    logger.warning("\(message, privacy: .public)")
    FileHandle.standardError.write(Data(("op-approval-watcher: " + message + "\n").utf8))
}

func nowMs() -> Double {
    Date().timeIntervalSince1970 * 1000
}

func json(_ value: Any) -> String {
    guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed]),
          let text = String(data: data, encoding: .utf8) else { return "null" }
    return text
}

// ---------------------------------------------------------------------------
// Paths

let env = ProcessInfo.processInfo.environment
let home = env["HOME"] ?? NSHomeDirectory()
let watcherDir = env["OP_APPROVAL_WATCHER_DIR"] ?? home + "/.local/share/op-approval-watcher"
let libDir = env["OP_APPROVAL_LIB"] ?? home + "/.agents/lib/op-approval"
let configFile = (env["XDG_CONFIG_HOME"] ?? home + "/.config") + "/op-approval/config.json"
let onePasswordLog = home + "/Library/Group Containers/2BUA8C4S2C.com.1password/Library/Application Support/1Password/Data/logs/1Password_rCURRENT.log"

// Same rule as common.sh: the per-user temporary directory, never $TMPDIR.
func runtimeDir() -> String? {
    if let dir = env["OP_APPROVAL_RUNTIME_DIR"], !dir.isEmpty { return dir }
    var buffer = [CChar](repeating: 0, count: Int(PATH_MAX))
    guard confstr(_CS_DARWIN_USER_TEMP_DIR, &buffer, buffer.count) > 0 else { return nil }
    let base = String(cString: buffer)
    return (base.hasSuffix("/") ? base : base + "/") + "op-approval"
}

guard let feedDir = runtimeDir() else {
    warn("cannot find the per-user temporary directory")
    exit(1)
}
let feedFile = feedDir + "/presence.json"

func readText(_ path: String) -> String? {
    try? String(contentsOfFile: path, encoding: .utf8)
}

// A file's text for an event, or JSON null when it cannot be read.
func textOrNull(_ path: String) -> Any {
    readText(path) ?? NSNull()
}

// ---------------------------------------------------------------------------
// Engine

let context = JSContext()!
context.exceptionHandler = { _, exception in
    warn("engine error: \(exception?.toString() ?? "unknown")")
}

guard let policySource = readText(watcherDir + "/Policy.js"),
      let engineSource = readText(watcherDir + "/Engine.js") else {
    warn("cannot read Policy.js and Engine.js in \(watcherDir)")
    exit(1)
}
context.evaluateScript(policySource, withSourceURL: URL(fileURLWithPath: watcherDir + "/Policy.js"))
context.evaluateScript(engineSource, withSourceURL: URL(fileURLWithPath: watcherDir + "/Engine.js"))
context.evaluateScript("""
    var __engine = createEngine(POLICY);
    var __state = __engine.initial();
    function __step(eventJson) {
        var r = __engine.step(__state, JSON.parse(eventJson));
        __state = r.state;
        return JSON.stringify(r.effects);
    }
    function __policy(name, argsJson) {
        return JSON.stringify(POLICY[name].apply(null, JSON.parse(argsJson)));
    }
    """)
guard context.objectForKeyedSubscript("__engine")?.isUndefined == false else {
    warn("Engine.js did not load")
    exit(1)
}

func policy(_ name: String, _ args: [Any]) -> Any? {
    guard let out = context.objectForKeyedSubscript("__policy")?.call(withArguments: [name, json(args)])?.toString(),
          let data = out.data(using: .utf8) else { return nil }
    return try? JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed])
}

func windowArg(_ w: WindowInfo) -> [String: Any] {
    ["owner": w.owner, "layer": w.layer, "width": w.width, "onScreen": w.onScreen]
}

func classify(_ w: WindowInfo) -> String? {
    policy("macCandidateSource", [windowArg(w)]) as? String
}

// Events are queued so an effect answered at once (an observation) is
// handled after the effects of the step that asked for it.
var queue: [[String: Any]] = []
var draining = false

func send(_ event: [String: Any]) {
    var e = event
    if e["atMs"] == nil { e["atMs"] = nowMs() }
    queue.append(e)
    guard !draining else { return }
    draining = true
    while !queue.isEmpty {
        let next = queue.removeFirst()
        guard let out = context.objectForKeyedSubscript("__step")?.call(withArguments: [json(next)])?.toString(),
              let data = out.data(using: .utf8),
              let effects = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
            warn("the engine returned no effects for a \(next["type"] ?? "?") event")
            continue
        }
        for effect in effects { apply(effect) }
    }
    draining = false
}

// ---------------------------------------------------------------------------
// Signals

let windows = WindowTracker()
let input = InputMonitor()
let logFollower = LogFollower(path: onePasswordLog)

func listWindows() -> [WindowInfo] {
    let list = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID) as? [[String: Any]] ?? []
    return list.compactMap { w in
        guard let number = w[kCGWindowNumber as String] as? Int else { return nil }
        let bounds = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
        return WindowInfo(
            number: number,
            owner: w[kCGWindowOwnerName as String] as? String ?? "",
            layer: w[kCGWindowLayer as String] as? Int ?? 0,
            width: (bounds["Width"] as? NSNumber)?.doubleValue ?? 0,
            onScreen: w[kCGWindowIsOnscreen as String] as? Bool ?? false)
    }
}

func hidIdleSeconds() -> Double {
    CGEventSource.secondsSinceLastEventType(.hidSystemState, eventType: CGEventType(rawValue: ~0)!)
}

func sessionReading() -> (lock: String, session: String) {
    guard let d = CGSessionCopyCurrentDictionary() as? [String: Any] else { return ("unknown", "inactive") }
    let locked = d["CGSSessionScreenIsLocked"] as? Bool ?? false
    let onConsole = d["kCGSSessionOnConsoleKey"] as? Bool ?? false
    return (locked ? "locked" : "unlocked", onConsole ? "up" : "inactive")
}

// The config file's identity and size, to notice a change between the
// engine's own reads.
func configStamp() -> String {
    guard let a = try? FileManager.default.attributesOfItem(atPath: configFile) else { return "missing" }
    let modified = (a[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0
    return "\(a[.systemFileNumber] ?? 0):\(a[.size] ?? 0):\(modified)"
}

var lastConfigStamp = configStamp()

func checkConfig() {
    let stamp = configStamp()
    guard stamp != lastConfigStamp else { return }
    lastConfigStamp = stamp
    send(["type": "config", "text": textOrNull(configFile)])
}

// Input first: a click that answers a prompt is then seen before its close.
func poll() {
    let now = nowMs()
    for e in input.sample(idleSeconds: hidIdleSeconds(), nowMs: now) {
        switch e {
        case .idle(let at): send(["type": "input", "state": "idle", "atMs": at])
        case .active(let at): send(["type": "input", "state": "active", "atMs": at])
        }
    }
    for change in windows.update(listWindows(), classify: classify) {
        switch change {
        case .opened(let key, let source):
            send(["type": "candidate_open", "key": String(key), "openedAtMs": now, "reconciled": false, "source": source])
        case .closed(let key):
            send(["type": "candidate_closed", "key": String(key), "closedAtMs": now])
        }
    }
    for line in logFollower.poll() {
        send(["type": "log_line", "line": line])
    }
    if logFollower.readable != logReadable {
        logReadable = logFollower.readable
        if logReadable {
            info("following 1Password's log")
        } else {
            info("1Password's log is not readable (macOS protects other apps' data); "
                + "approvals are judged without it, so browser extension unlocks are not detected")
        }
    }
}

var logReadable = true

// ---------------------------------------------------------------------------
// Effects

var timers: [String: DispatchSourceTimer] = [:]

func apply(_ effect: [String: Any]) {
    switch effect["type"] as? String {
    case "log":
        let message = effect["message"] as? String ?? ""
        if effect["level"] as? String == "warn" { warn(message) } else { info(message) }
    case "write_feed":
        writeFeed(effect["document"] ?? [:])
    case "run":
        runHelper(effect)
    case "observe":
        let id = effect["id"] as? String ?? ""
        send(["type": "observed", "id": id, "result": observe(effect["what"] as? String ?? "", key: effect["key"] as? String)])
    case "reset_input":
        input.reset()
    case "set_timer":
        let id = effect["id"] as? String ?? ""
        let delay = (effect["delayMs"] as? NSNumber)?.doubleValue ?? 1
        // An explicit leeway: by default macOS lets a background process's
        // timer run up to 10% late (12 s on the 120 s grace period).
        let timer = DispatchSource.makeTimerSource(queue: .main)
        timer.schedule(deadline: .now() + delay / 1000, leeway: .milliseconds(50))
        timer.setEventHandler {
            timer.cancel()
            timers[id] = nil
            send(["type": "timer_fired", "id": id])
        }
        timers[id] = timer
        timer.resume()
    case "cancel_timer":
        let id = effect["id"] as? String ?? ""
        timers.removeValue(forKey: id)?.cancel()
    case "exit":
        let code = (effect["code"] as? NSNumber)?.int32Value ?? 1
        info("exiting (\(code))")
        exit(code)
    default:
        warn("unknown effect \(effect["type"] ?? "?")")
    }
}

func observe(_ what: String, key: String?) -> Any {
    switch what {
    case "candidate":
        let w = key.flatMap { Int($0) }.flatMap { windows.current[$0] }
        let source = w.map { classify($0) ?? "" } ?? ""
        let result = policy("macConfirm", [source, w.map(windowArg) ?? NSNull()])
        return result ?? ["confirmed": false, "reason": "confirmation failed"]
    case "open_candidates":
        // Only 1Password approval windows can be reconciled; the system
        // Touch ID dialog needs the unlock request that came before it.
        let open = windows.adoptOpen(classify: { classify($0) == "approval" ? "approval" : nil })
        return ["candidates": open.map { ["key": String($0.key), "source": $0.source] }]
    case "lock":
        return ["state": sessionReading().lock]
    case "session":
        return ["state": sessionReading().session]
    case "config":
        return ["text": textOrNull(configFile)]
    case "code":
        return ["policy": textOrNull(watcherDir + "/Policy.js"), "engine": textOrNull(watcherDir + "/Engine.js")]
    default:
        return NSNull()
    }
}

// The feed and its directory are private: mode 600 in 700, written through a
// temporary file and a rename so readers never see half a document.
func writeFeed(_ document: Any) {
    let fm = FileManager.default
    var isDir: ObjCBool = false
    if let attrs = try? fm.attributesOfItem(atPath: feedDir), attrs[.type] as? FileAttributeType == .typeSymbolicLink {
        warn("refusing to use \(feedDir): it is a symlink")
        return
    }
    if !fm.fileExists(atPath: feedDir, isDirectory: &isDir) {
        do {
            try fm.createDirectory(atPath: feedDir, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        } catch {
            warn("cannot create \(feedDir)")
            return
        }
    }
    chmod(feedDir, 0o700)
    let tmp = feedFile + ".tmp.\(getpid())"
    let text = json(document) + "\n"
    guard fm.createFile(atPath: tmp, contents: Data(text.utf8), attributes: [.posixPermissions: 0o600]),
          rename(tmp, feedFile) == 0 else {
        unlink(tmp)
        warn("cannot write the presence feed")
        return
    }
}

func helperPath(_ name: String) -> String? {
    switch name {
    case "requesters": return watcherDir + "/requesters"
    case "locate", "claim", "publish": return libDir + "/" + name
    default: return nil
    }
}

// Runs a helper without blocking; reports its exit code and output, or -1
// with no output when it is still running at its deadline (it is killed).
func runHelper(_ effect: [String: Any]) {
    let id = effect["id"] as? String ?? ""
    let args = effect["args"] as? [String] ?? []
    let deadline = (effect["deadlineMs"] as? NSNumber)?.doubleValue ?? 10000
    guard let path = helperPath(effect["helper"] as? String ?? "") else {
        send(["type": "helper_done", "id": id, "code": -1, "output": ""])
        return
    }
    let process = Process()
    process.executableURL = URL(fileURLWithPath: path)
    process.arguments = args
    let out = Pipe()
    process.standardOutput = out
    process.standardError = FileHandle.nullDevice
    process.standardInput = FileHandle.nullDevice
    var done = false
    let finish = { (code: Int, output: String) in
        guard !done else { return }
        done = true
        send(["type": "helper_done", "id": id, "code": code, "output": output])
    }
    do {
        try process.run()
    } catch {
        finish(-1, "")
        return
    }
    DispatchQueue.global().async {
        let data = out.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let code = process.terminationReason == .exit ? Int(process.terminationStatus) : -1
        DispatchQueue.main.async { finish(code, String(decoding: data, as: UTF8.self)) }
    }
    DispatchQueue.main.asyncAfter(deadline: .now() + deadline / 1000) {
        guard !done else { return }
        kill(process.processIdentifier, SIGKILL)
        finish(-1, "")
    }
}

// ---------------------------------------------------------------------------
// Start

signal(SIGPIPE, SIG_IGN)

let distributed = DistributedNotificationCenter.default()
for name in ["com.apple.screenIsLocked", "com.apple.screenIsUnlocked"] {
    distributed.addObserver(forName: Notification.Name(name), object: nil, queue: .main) { _ in
        send(["type": "lock", "state": sessionReading().lock])
    }
}
let workspace = NSWorkspace.shared.notificationCenter
workspace.addObserver(forName: NSWorkspace.willSleepNotification, object: nil, queue: .main) { _ in
    send(["type": "sleep"])
}
workspace.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { _ in
    send(["type": "wake"])
}

// The local host name from System Settings > Sharing, as the shell scripts
// use: the kernel hostname follows the network and can change.
let hostname = (SCDynamicStoreCopyLocalHostName(nil) as String?) ?? ""
let runId = String((0..<4).map { _ in "abcdefghijklmnopqrstuvwxyz0123456789".randomElement()! })

// The first poll records the windows open at start, which are never new.
_ = windows.update(listWindows(), classify: classify)
_ = logFollower.poll()

send([
    "type": "start",
    "previousFeed": textOrNull(feedFile),
    "config": textOrNull(configFile),
    "hostname": hostname,
    "runId": runId,
    "code": ["policy": policySource, "engine": engineSource],
])

Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { _ in poll() }
Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
    checkConfig()
    send(["type": "tick"])
}
RunLoop.main.run()
