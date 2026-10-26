---
name: windows-vm
description: Control the Windows 11 VM that runs in VMware Workstation on this Omarchy machine (the VM for Autodesk Fusion). Take screenshots to see its screen, run PowerShell or cmd inside Windows, copy files in and out, launch apps on the Windows desktop, list processes, check whether it is running, and shut it down. Use whenever the user mentions the Windows VM, Windows, VMware or "the VM", asks what is on the Windows screen, or wants something installed, checked, configured, fixed or fetched in Windows, even if they never say "VM". For modelling work inside Fusion, prefer the fusion MCP server's tools.
---

# Windows VM

The VM is `~/vmware/Fusion-Win11/Fusion-Win11.vmx`. It is often off. Everything goes through `winvm`, which this skill's package puts on `PATH` (it is also `scripts/winvm` next to this file). Run `winvm --help` for the full syntax.

| Task | Command |
| --- | --- |
| Is it on? IP address? | `winvm status` |
| See the screen | `winvm screenshot [file.png]`, then read the printed PNG (default `$TMPDIR` or `/tmp`; pass a path in your scratch directory if you have one) |
| Run PowerShell | `winvm ps -c 'Get-Service sshd'`, `winvm ps script.ps1`, or a heredoc on stdin |
| Run cmd.exe | `winvm cmd -c 'ipconfig /all'` |
| Copy files | `winvm push <host-file> <win-path>`, `winvm pull <win-path> <host-file>` |
| Open an app for the user | `winvm launch 'C:\Windows\notepad.exe' 'C:\path\file.txt'` |
| Processes | `winvm processes` |
| Start or stop | `winvm start`, `winvm stop` |

## How commands run

- Through VMware Tools, as the auto sign-in administrator, already elevated. The credentials come from `guest-user` and `guest-password` next to the vmx. Never print or copy the password.
- `ps` and `cmd` run hidden and wait until the program exits, then print its combined output and exit with its exit code. Anything that waits for input or opens a window hangs, so pass `-Force`, `-Confirm:$false`, `/quiet` and similar, and use `launch` for anything the user should see.
- PowerShell is Windows PowerShell 5.1. A non-terminating error prints but still exits 0, so add `-ErrorAction Stop` or check the output.
- Multi-line PowerShell is easiest as a heredoc (`winvm ps <<'EOF'`), which avoids shell and Windows quoting together.
- A `ps` or `cmd` call takes about 4 seconds (copy in, run, copy out, clean up). Batch related work into one script.

## Seeing the screen

`winvm screenshot` captures the VM's display at full resolution (3440×1440 at the moment) in about 0.2 seconds. It works while Windows is locked, showing the lock screen. Take one before and after anything that changes what is on screen, and when the user says "look at this" or describes something they see.

There's no mouse control. `vmcli <vmx> MKS sendKeySequence` and `sendKeyEvent` exist but are untested, and they type into whatever window has focus (often Fusion), so ask the user before trying them.

## Moving files

`push` and `pull` suit single files. For larger or repeated transfers, use the shared folders, which Windows maps at sign-in:

| Host | Windows |
| --- | --- |
| `~/Documents/Windows-Bridge` | `Z:` |
| `~/Downloads/3D Printing` | `Y:` |

Paths must be complete Windows paths. `C:\Windows\Temp` is a safe scratch location. Clean up what you put there.

## Power

- `winvm status` first. If the VM is off, say so, and ask the user before starting it.
- `winvm start` fails inside apps that set `NoNewPrivs` (Claude Desktop, for one), because VMware's `vmware-vmx` is set-UID. The error prints the command for the user to run in a terminal. Don't try to get around it.
- `winvm stop` shuts Windows down. Fusion may have unsaved work, so always ask first.

## Background

Setup, settings, shared folders, Remote Desktop and the Fusion MCP tunnel are documented in `docs/windows-vm.md` in the dotfiles repository.
