// The macOS requesters helper, run for real against stand-in processes:
// processes started through links named op, 1Password and ssh. macOS only.
// Run from the repository root:
//   node --test packages/macos/op-approval-watcher/tests/
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { execFileSync, spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const REQUESTERS = path.resolve(__dirname, "../.local/share/op-approval-watcher/requesters");
const darwin = { skip: process.platform !== "darwin" };

function requesters(home, args, extraEnv = {}) {
    const out = execFileSync(REQUESTERS, args, {
        env: { PATH: process.env.PATH, HOME: home, ...extraEnv },
        encoding: "utf8"
    });
    return JSON.parse(out);
}

function tempHome(t) {
    // Short path: Unix socket paths are limited to about 100 bytes.
    const home = fs.mkdtempSync(path.join("/tmp", "opa-req-"));
    t.after(() => fs.rmSync(home, { recursive: true, force: true }));
    return home;
}

function start(t, file, args) {
    const child = spawn(file, args, { stdio: ["ignore", "pipe", "inherit"] });
    t.after(() => child.kill());
    return child;
}

function linked(home, name, target) {
    const link = path.join(home, name);
    fs.symlinkSync(target, link);
    return link;
}

async function until(check) {
    const deadline = Date.now() + 10_000;
    while (!check()) {
        if (Date.now() > deadline) throw new Error("timed out");
        await new Promise(r => setTimeout(r, 20));
    }
}

test("an op process counts only if it started no later than the window and at most 5 s before", darwin, async (t) => {
    const home = tempHome(t);
    const before = Date.now();
    const child = start(t, linked(home, "op", "/bin/sleep"), ["30"]);
    await until(() => execFileSync("ps", ["-o", "comm=", "-p", String(child.pid)], { encoding: "utf8" }).trim().endsWith("/op"));
    const after = Date.now();
    const opPids = openedAtMs => requesters(home, ["--opened-at", (openedAtMs / 1000).toFixed(3)])
        .candidates.filter(c => c.source === "op").map(c => c.pid);

    assert.ok(opPids(after + 500).includes(child.pid), "started shortly before the window");
    assert.ok(!opPids(before - 2_000).includes(child.pid), "started after the window opened");
    assert.ok(!opPids(after + 7_000).includes(child.pid), "started more than 5 s before the window");
    assert.ok(requesters(home, ["--reconciled"]).candidates.some(c => c.pid === child.pid), "young enough when reconciled");
});

// lsof names a process by its executable, so the stand-ins are real binaries
// named 1Password, ssh-agent, ssh and git: one small program that listens on
// or connects to the socket it is given, then waits.
const SOCKET_PROGRAM = `
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
int main(int argc, char **argv) {
    struct sockaddr_un a = { .sun_family = AF_UNIX };
    strncpy(a.sun_path, argv[2], sizeof a.sun_path - 1);
    int s = socket(AF_UNIX, SOCK_STREAM, 0);
    if (argv[1][0] == 'l') {
        if (bind(s, (struct sockaddr *)&a, sizeof a) || listen(s, 4)) return 1;
        write(1, "ready\\n", 6);
        for (;;) accept(s, 0, 0);
    }
    if (connect(s, (struct sockaddr *)&a, sizeof a)) return 1;
    write(1, "ready\\n", 6);
    pause();
}
`;

test("a client of a socket 1Password holds is a requester; a client of another agent's socket is not", darwin, async (t) => {
    const home = tempHome(t);
    const source = path.join(home, "socket.c");
    fs.writeFileSync(source, SOCKET_PROGRAM);
    const binary = name => {
        const file = path.join(home, name);
        execFileSync("cc", ["-o", file, source]);
        return file;
    };
    const agentSock = path.join(home, "agent.sock");
    const otherSock = path.join(home, "other.sock");
    const ready = child => new Promise(r => child.stdout.once("data", r));

    const onePassword = start(t, binary("1Password"), ["listen", agentSock]);
    const other = start(t, binary("ssh-agent"), ["listen", otherSock]);
    await Promise.all([ready(onePassword), ready(other)]);
    const ssh = start(t, binary("ssh"), ["connect", agentSock]);
    const unrelated = start(t, binary("git"), ["connect", otherSock]);
    await Promise.all([ready(ssh), ready(unrelated)]);

    // Two candidate paths (launchd sets SSH_AUTH_SOCK to Apple's agent).
    fs.mkdirSync(path.join(home, ".ssh"));
    fs.writeFileSync(path.join(home, ".ssh", "config"), `Host *\n  IdentityAgent "${otherSock}"\n`);

    for (const sock of [agentSock, otherSock]) {
        const result = requesters(home, ["--opened-at", String(Date.now() / 1000)], { SSH_AUTH_SOCK: sock });
        const sshPids = result.candidates.filter(c => c.source === "ssh-agent").map(c => c.pid);
        if (sock === agentSock) {
            assert.deepEqual(result.sockets, [agentSock]);
            assert.deepEqual(sshPids, [ssh.pid]);
            assert.equal(result.candidates.find(c => c.pid === ssh.pid).comm, "ssh");
        } else {
            assert.deepEqual(result.sockets, []);
            assert.deepEqual(sshPids, []);
        }
    }
});
