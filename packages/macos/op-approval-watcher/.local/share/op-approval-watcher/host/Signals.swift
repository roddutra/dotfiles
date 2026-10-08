// Translation of macOS signals into engine events: window list changes,
// HID idle readings and 1Password log lines. No decisions: which windows can
// be approvals and when one is confirmed come from Policy.js, passed in as
// `classify`. Free of AppKit so the tests compile it on its own.
import Foundation

struct WindowInfo: Equatable {
    let number: Int
    let owner: String
    let layer: Int
    let width: Double
    let onScreen: Bool
}

enum WindowChange: Equatable {
    case opened(key: Int, source: String)
    case closed(key: Int)
}

// Reports a window once, when a window that was not listed when the watcher
// started first matches `classify`, and reports it closed when it leaves the
// list or, after being shown, is hidden again.
final class WindowTracker {
    private var baseline: Set<Int>?
    private var reported: Set<Int> = []
    private var tracked: [Int: Bool] = [:]  // key -> shown since it was reported
    private(set) var current: [Int: WindowInfo] = [:]

    func update(_ windows: [WindowInfo], classify: (WindowInfo) -> String?) -> [WindowChange] {
        current = Dictionary(windows.map { ($0.number, $0) }, uniquingKeysWith: { a, _ in a })
        guard let baseline = baseline else {
            self.baseline = Set(current.keys)
            return []
        }
        var changes: [WindowChange] = []
        for key in tracked.keys.sorted() {
            guard let w = current[key] else {
                tracked[key] = nil
                changes.append(.closed(key: key))
                continue
            }
            if w.onScreen {
                tracked[key] = true
            } else if tracked[key] == true {
                tracked[key] = nil
                changes.append(.closed(key: key))
            }
        }
        for w in windows.sorted(by: { $0.number < $1.number })
        where !baseline.contains(w.number) && !reported.contains(w.number) {
            guard let source = classify(w) else { continue }
            reported.insert(w.number)
            tracked[w.number] = w.onScreen
            changes.append(.opened(key: w.number, source: source))
        }
        // Window numbers are not reused soon; forget the ones that are gone.
        reported.formIntersection(current.keys)
        return changes
    }

    // Windows already listed at start that may be approvals; they are
    // tracked from now on, so their close is reported.
    func adoptOpen(classify: (WindowInfo) -> String?) -> [(key: Int, source: String)] {
        var found: [(key: Int, source: String)] = []
        for w in current.values.sorted(by: { $0.number < $1.number }) where tracked[w.number] == nil {
            guard let source = classify(w), w.onScreen else { continue }
            reported.insert(w.number)
            tracked[w.number] = true
            found.append((key: w.number, source: source))
        }
        return found
    }
}

enum InputEvent: Equatable {
    case idle(atMs: Double)
    case active(atMs: Double)
}

// A 5-second input monitor over the seconds since the last HID event, like
// Omarchy's IdleMonitor: after a reset it reports nothing until 5 s pass
// without input, then "idle", then "active" stamped with the real input time
// on every new input.
final class InputMonitor {
    static let idleSeconds = 5.0
    private var reportedIdle = false
    private var idle = false
    private var last: Double?

    func reset() {
        reportedIdle = false
        idle = false
        last = nil
    }

    func sample(idleSeconds: Double, nowMs: Double) -> [InputEvent] {
        defer { last = idleSeconds }
        let newInput = last.map { idleSeconds + 0.05 < $0 } ?? false
        let inputAtMs = nowMs - idleSeconds * 1000
        if idle {
            guard newInput || idleSeconds < InputMonitor.idleSeconds else { return [] }
            idle = false
            return [.active(atMs: inputAtMs)]
        }
        if idleSeconds >= InputMonitor.idleSeconds {
            idle = true
            reportedIdle = true
            return [.idle(atMs: nowMs)]
        }
        return reportedIdle && newInput ? [.active(atMs: inputAtMs)] : []
    }
}

// Follows a log file by name: starts at its end, reopens it when it is
// replaced or truncated (1Password rotates at about 500 KB), and returns
// complete new lines. `readable` is false while the file exists but cannot
// be opened (macOS protects other apps' data from background processes).
final class LogFollower {
    let path: String
    private(set) var readable = true
    private var handle: FileHandle?
    private var inode: UInt64 = 0
    private var offset: UInt64 = 0
    private var partial = Data()
    private var polled = false

    init(path: String) {
        self.path = path
    }

    func poll() -> [String] {
        let firstPoll = !polled
        polled = true
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: path),
              let ino = (attrs[.systemFileNumber] as? NSNumber)?.uint64Value,
              let size = (attrs[.size] as? NSNumber)?.uint64Value else {
            close()
            return []
        }
        if handle == nil || ino != inode || size < offset {
            close()
            // An unfinished line in the old file never continues in the new one.
            partial.removeAll()
            guard let h = FileHandle(forReadingAtPath: path) else {
                readable = false
                return []
            }
            readable = true
            handle = h
            inode = ino
            // The file found at start is followed from its end; a later or
            // replacement file from its start, since everything in it is new.
            offset = firstPoll ? size : 0
        }
        guard let h = handle, size > offset else { return [] }
        do {
            try h.seek(toOffset: offset)
            let data = h.readData(ofLength: Int(min(size - offset, 1 << 20)))
            offset += UInt64(data.count)
            partial.append(data)
        } catch {
            close()
            return []
        }
        var lines: [String] = []
        while let nl = partial.firstIndex(of: 0x0A) {
            let line = partial[partial.startIndex..<nl]
            partial.removeSubrange(partial.startIndex...nl)
            lines.append(String(decoding: line, as: UTF8.self))
        }
        if partial.count > 65536 { partial.removeAll() }
        return lines
    }

    private func close() {
        try? handle?.close()
        handle = nil
    }
}
