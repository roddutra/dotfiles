# UpSnap control of the Mac

[UpSnap](https://github.com/seriousm4x/UpSnap) runs in Docker with host networking on another machine on the home LAN. It controls the MacBook Pro (M1 Pro) over SSH with three restricted keys, one per action. Network wake alone can't do the job on this Mac, for these reasons:

- The Mac wakes into a background (dark) wake for almost any packet, answers ping and SSH, and stays dark, so ping always reports it online.
- Apple silicon MacBooks have no built-in Ethernet, and the USB Ethernet adapter (Realtek RTL8153 on a USB-C hub) doesn't wake the Mac from sleep.
- Wi-Fi can wake it, but network wakes are dark wakes with the display off.

| UpSnap action | Key comment | Forced command |
| --- | --- | --- |
| Status | `mbp-status` | `~/.local/bin/upsnap-display-awake` |
| Wake | `mbp-wake` | `/usr/bin/caffeinate -u -t 5` |
| Sleep | `mbp sleep` | `sudo -n /usr/bin/pmset sleepnow` |

UpSnap targets both the Wi-Fi and the Ethernet address of the Mac. Both are DHCP with router reservations. The Wi-Fi network uses a **Fixed** private Wi-Fi address (System Settings > Wi-Fi > Details > Private Wi-Fi address), so the reservation and UpSnap's MAC stay valid. Rotating would break both.

## Status: `upsnap-display-awake`

Package `packages/macos/upsnap` installs `~/.local/bin/upsnap-display-awake`. It prints one word and exits:

- `0` and `awake` when the system has the Graphics capability (`pmset -g systemstate`) and WindowServer reports the main display awake (`CGDisplayIsAsleep(CGMainDisplayID())` through `osascript`).
- `1` and `display-off` for display sleep, a dark wake, or any error.

UpSnap treats exit 0 as online, and exit 1, a timeout or a refused connection as offline. A fully asleep Mac can't answer at all.

Why this check:

- It works from a non-GUI SSH session without sudo and takes about 0.1 s (0.5 s cold).
- A locked screen with the display on reports awake.
- The main display is the built-in panel with the lid open and the external display in clamshell mode. macOS sleeps all displays together, so one display stands for all.
- IOKit has no usable signal. `IODisplayWrangler` exists but has no power state, and `AppleCLCD2` and DCP power states stay at 1 with the display off.
- Brightness and backlight values (`IOMFBBrightnessLevel`, `AppleARMBacklight` `CurrentNits`) are not used, because the screen is sometimes dimmed to zero.
- `pmset -g log` records display on and off but takes over 20 s to read.

## Wake: `caffeinate -u`

`caffeinate -u` declares user activity, which turns the display on and turns a dark wake into a full wake. Tested from a non-GUI SSH session after `pmset displaysleepnow`: the display came on with nobody touching the Mac. The session stays open for about 5.4 s, so UpSnap's wake timeout must be at least 10 s. `pmset schedule wake` isn't used, because it needs root and only fires from full sleep.

## Sleep: `pmset sleepnow`

The kernel accepts a sleep request only from root or from the logged-in console session. A forced SSH command runs in a separate session, so it goes through sudo. The drop-in `/etc/sudoers.d/upsnap-sleep` (mode 0440, root:wheel) allows exactly that command:

```text
<user> ALL=(root) NOPASSWD: /usr/bin/pmset sleepnow
```

Other `pmset` arguments still need a password. `sudo -l /usr/bin/pmset ...` reports every variant as allowed because of the admin `(ALL) ALL` rule, so check the full `sudo -n -l` listing instead. Expect the sleep SSH call to end with a dropped connection.

## Set up on a new Mac

1. Turn on System Settings > General > Sharing > Remote Login. The user must be allowed, directly or through the admin group.
2. Apply the dotfiles so `~/.local/bin/upsnap-display-awake` exists.
3. Install the sudoers drop-in above, then run `sudo visudo -c`.
4. Turn on Wake for network access on power adapter: `sudo pmset -c womp 1`.
5. Add the three keys to `~/.ssh/authorized_keys` (mode 600, `~/.ssh` mode 700). Use the absolute home path, because forced commands don't expand `~`:

   ```text
   from="<upsnap-host-ip>",restrict,command="<home>/.local/bin/upsnap-display-awake" ssh-ed25519 <key> upsnap@docker-services-lxc mbp-status
   from="<upsnap-host-ip>",restrict,command="/usr/bin/caffeinate -u -t 5" ssh-ed25519 <key> upsnap@docker-services-lxc mbp-wake
   from="<upsnap-host-ip>",restrict,command="sudo -n /usr/bin/pmset sleepnow" ssh-ed25519 <key> upsnap@docker-services-lxc mbp sleep
   ```

6. For a new sleep key, start with `command="echo ok"` and swap in the real command once UpSnap's dry run prints `ok`.

## Sleep behaviour

- **Status checks:** with `restrict` there is no pty, so `ttyskeepawake` doesn't apply, and SSH logins don't count as user activity. They don't keep an awake Mac awake.
- **Packets during sleep:** every check or ping to a sleeping Mac causes a dark wake of about 10 s. While the UpSnap page is open and polling every few seconds, the Mac stays in back-to-back dark wakes with the display off, and status correctly reads offline. It settles back to sleep about 10 s after polling stops. Don't use ping status for this device.
- **On battery:** `womp` is 0, so there are no network wakes. With the lid closed and no external display, a wake is likely to drop straight back to sleep.
- **Idle-sleep blockers:** long-running `caffeinate` assertions block idle sleep but not `pmset sleepnow`. T3 Code runs `caffeinate -i -w <pid>` while a thread is working, and keeps LAN connections to Omarchy. The pmset log showed 0 to 2 Wi-Fi dark wakes per hour overnight, so that link isn't what causes frequent wakes.
- **Not yet tested:** wake from full system sleep (as opposed to display sleep) through the `mbp-wake` key.
