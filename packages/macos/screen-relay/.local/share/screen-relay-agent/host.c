/*
 * Permission holder for the screen-relay LaunchAgent.
 *
 * macOS grants Screen Recording and Accessibility to a process's
 * "responsible" process. Under launchd that is the job's own program, so
 * without this host the grant would have to go to node or /bin/sh, which
 * would extend it to every launchd job that runs them. This host stays the
 * job's program, starts PROGRAM as a child (which inherits responsibility),
 * forwards termination signals and exits with the child's status.
 *
 * Usage: screen-relay-host PROGRAM [ARG...]
 */
#include <errno.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>

extern char **environ;

static volatile pid_t child = 0;

static void forward(int sig) {
    if (child > 0) kill(child, sig);
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s PROGRAM [ARG...]\n", argv[0]);
        return 64;
    }

    struct sigaction action;
    memset(&action, 0, sizeof action);
    action.sa_handler = forward;
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGHUP, &action, NULL);

    pid_t pid;
    int rc = posix_spawn(&pid, argv[1], NULL, NULL, argv + 1, environ);
    if (rc != 0) {
        fprintf(stderr, "screen-relay-host: cannot start %s: %s\n", argv[1], strerror(rc));
        return 71;
    }
    child = pid;

    int status;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR) return 71;
    }
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    return 128 + WTERMSIG(status);
}
