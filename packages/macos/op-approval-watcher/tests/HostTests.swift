// Translation of macOS signals into engine events (host/Signals.swift),
// compiled with it into one program by host.test.js. The decisions those
// events feed are covered by the engine scenarios.
import Foundation

var failures = 0

func check(_ condition: Bool, _ message: String, line: Int = #line) {
    if !condition {
        failures += 1
        print("FAIL line \(line): \(message)")
    }
}

func win(_ number: Int, _ owner: String, _ layer: Int, _ width: Double, _ onScreen: Bool = true) -> WindowInfo {
    WindowInfo(number: number, owner: owner, layer: layer, width: width, onScreen: onScreen)
}

// Stands in for Policy.macCandidateSource.
func source(_ w: WindowInfo) -> String? {
    w.owner == "1Password" && w.layer == 101 ? "approval" : nil
}

// Windows: Quick Access (persistent, layer 101), the main window, and new
// approval windows as discovery saw them.
do {
    let t = WindowTracker()
    let quickAccess = win(10, "1Password", 101, 550, false)
    let main = win(11, "1Password", 0, 1024)
    check(t.update([quickAccess, main], classify: source) == [], "windows open at start are never new")
    check(t.update([win(10, "1Password", 101, 550, true), main], classify: source) == [], "Quick Access shown")
    check(t.update([quickAccess, main], classify: source) == [], "Quick Access hidden")

    // Created hidden at layer 0, then moved to layer 101, then shown.
    check(t.update([quickAccess, main, win(20, "1Password", 0, 0, false)], classify: source) == [], "not yet at layer 101")
    check(t.update([quickAccess, main, win(20, "1Password", 101, 400, false)], classify: source)
        == [.opened(key: 20, source: "approval")], "reported when it reaches layer 101")
    check(t.update([quickAccess, main, win(20, "1Password", 101, 400, true)], classify: source) == [], "reported once")
    check(t.update([quickAccess, main], classify: source) == [.closed(key: 20)], "closed when it leaves the list")

    // Hidden again after being shown also closes it, once.
    let open = t.update([quickAccess, main, win(21, "1Password", 101, 400, true)], classify: source)
    check(open == [.opened(key: 21, source: "approval")], "second approval")
    check(t.update([quickAccess, main, win(21, "1Password", 101, 400, false)], classify: source)
        == [.closed(key: 21)], "closed when hidden after being shown")
    check(t.update([quickAccess, main], classify: source) == [], "no second close")

    check(t.update([quickAccess, main, win(30, "Shottr", 101, 400)], classify: source) == [], "other owners are ignored")
}

// Reconciliation: approval windows already on screen at start are adopted
// and their close is reported; hidden ones are not.
do {
    let t = WindowTracker()
    let pending = win(40, "1Password", 101, 400, true)
    let quickAccess = win(10, "1Password", 101, 550, false)
    _ = t.update([pending, quickAccess], classify: source)
    let adopted = t.adoptOpen(classify: source)
    check(adopted.map { $0.key } == [40], "adopts the on-screen approval window only")
    check(t.update([quickAccess], classify: source) == [.closed(key: 40)], "reports the adopted window's close")
}

// Input: a 5 s monitor over HID idle seconds.
do {
    let m = InputMonitor()
    let t0 = 1_000_000.0
    check(m.sample(idleSeconds: 1, nowMs: t0) == [], "nothing before the first idle report")
    check(m.sample(idleSeconds: 0.2, nowMs: t0 + 1000) == [], "input before the first idle report is not reported")
    check(m.sample(idleSeconds: 5.2, nowMs: t0 + 6000) == [.idle(atMs: t0 + 6000)], "idle after 5 s")
    check(m.sample(idleSeconds: 6, nowMs: t0 + 6800) == [], "idle once")
    check(m.sample(idleSeconds: 0.1, nowMs: t0 + 7000) == [.active(atMs: t0 + 6900)], "active, stamped with the input time")
    check(m.sample(idleSeconds: 0.3, nowMs: t0 + 7200) == [], "no new input")
    check(m.sample(idleSeconds: 0.05, nowMs: t0 + 7400) == [.active(atMs: t0 + 7350)], "each new input while active")
    m.reset()
    check(m.sample(idleSeconds: 0.01, nowMs: t0 + 8000) == [], "silent again after a reset")
    check(m.sample(idleSeconds: 5, nowMs: t0 + 13000) == [.idle(atMs: t0 + 13000)], "idle after the reset")
}

// Log: follows the file by name from its end, across rotation.
do {
    let dir = FileManager.default.temporaryDirectory.appendingPathComponent("opa-host-test-\(getpid())")
    try! FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }
    let path = dir.appendingPathComponent("1Password_rCURRENT.log").path
    func append(_ text: String, to file: String = path) {
        let h = FileHandle(forWritingAtPath: file)!
        h.seekToEndOfFile()
        h.write(text.data(using: .utf8)!)
        try! h.close()
    }
    FileManager.default.createFile(atPath: path, contents: "old line\n".data(using: .utf8))
    let f = LogFollower(path: path)
    check(f.poll() == [], "starts at the end of the existing file")
    append("first\nsecond, partial")
    check(f.poll() == ["first"], "complete lines only")
    append(" end\n")
    check(f.poll() == ["second, partial end"], "a line split across writes")
    append("cut short by rotation")
    check(f.poll() == [], "an unfinished line is held")
    try! FileManager.default.moveItem(atPath: path, toPath: dir.appendingPathComponent("1Password_r00001.log").path)
    FileManager.default.createFile(atPath: path, contents: "after rotation\n".data(using: .utf8))
    check(f.poll() == ["after rotation"], "a new file is read from its start")
    check(f.readable, "readable")

    // A file that exists but cannot be opened, as macOS presents another
    // app's protected data to a background process.
    let locked = dir.appendingPathComponent("locked.log").path
    FileManager.default.createFile(atPath: locked, contents: "x\n".data(using: .utf8), attributes: [.posixPermissions: 0])
    let blocked = LogFollower(path: locked)
    check(blocked.poll() == [] && !blocked.readable, "an unopenable file is reported as not readable")
}

if failures > 0 {
    print("\(failures) failure(s)")
    exit(1)
}
print("ok")
