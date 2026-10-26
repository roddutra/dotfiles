# Windows VM for Autodesk Fusion

Fusion has no Linux build. It runs in a Windows 11 Pro guest under VMware Workstation (`vmware-workstation` from the AUR), whose 3D acceleration gives the guest DirectX 11 on the host GPU without passing it through. The host has a single GPU, so passthrough would take the only display away from Hyprland.

The VM lives in `~/vmware/Fusion-Win11/` and is not tracked. `~/vmware` has copy-on-write turned off (`chattr +C`, set while empty), and `@home` is outside snapper's snapshots.

| Setting | Value |
| --- | --- |
| CPU | 6 cores, 1 socket |
| Memory | 12 GB, released when the VM is off |
| Disk | 128 GB NVMe, growable |
| Graphics | 3D on, 4 GB graphics memory |
| Firmware | UEFI with Secure Boot, no vTPM |
| Network | Bridged to `enp5s0`, `vmxnet3` (NAT and `e1000e` until VMware Tools is installed) |
| Audio | HD Audio through PipeWire |
| Removed | Floppy |

## Gotchas

- KVM claims AMD-V at module load since kernel 6.12 and never releases it, which stops VMware starting a VM. `system/omarchy/etc/modprobe.d/kvm-virt-on-demand.conf` sets `kvm.enable_virt_at_load=0`, so KVM only takes it while a KVM guest runs. `omarchy-windows-vm` still works.
- The `vmware-workstation` AUR metadata (26H1u1-4) omits `vmware-keymaps`, so `yay` fails with `Missing dependencies: vmware-keymaps`. The manifest lists it first. The metadata also pulls `uefitool` as a build dependency, which leaves `uefitool-debug` installed afterwards.
- `vmware-networks.service` starts at boot (`sudo systemctl enable --now vmware-networks.service`, about 12 MB). Started on demand by its `.path` unit, it came up a few seconds after the VM, which then started with `Could not connect 'Ethernet0' to virtual network '/dev/vmnet8'`. `vmware-usbarbitrator.path` still starts USB support only while a VM runs.
- No vTPM: `managedVM.autoAddVTPM = "software"` is experimental and has encrypted VMs with an unknown password. Setup bypasses the TPM check through `LabConfig` instead. Add an encrypted vTPM from VM Settings if BitLocker is ever needed.
- VMs can't be started from Claude Desktop: the app runs with `NoNewPrivs`, which blocks the set-UID `vmware-vmx`. Start them from a terminal or the launcher.

## Windows account

Windows signs in automatically to a local administrator account created by the answer file. Its password lives in `~/vmware/Fusion-Win11/guest-password` (mode 600, untracked, outside snapper's snapshots), with a copy in 1Password. It's needed:

- after locking Windows, signing out, or for Remote Desktop
- for `vmrun` guest commands (`-gu <user> -gp "$(cat ~/vmware/Fusion-Win11/guest-password)"`)
- by `winvm` (see "Agent skill"), which reads the user name from `guest-user` (mode 600, untracked) in the same folder

Admin prompts (UAC) only ask for consent for this account. A Windows Hello PIN unlocks the VM's own screen. It doesn't work for Remote Desktop or `vmrun`, and without a TPM its key is stored in software.

Auto sign-in keeps its own copy of the password, as the LSA secret `DefaultPassword`, with `AutoAdminLogon`, `DefaultUserName` and `DefaultDomainName` under `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`. After changing the password, update that copy, `guest-password` and 1Password. In `netplwiz` the checkbox is hidden until `DevicePasswordLessBuildVersion` is 0 under `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device`. Toggling it cleared the Winlogon values on 26 October 2026 and auto sign-in stopped, so prefer `docs/windows-vm/set-autologon.ps1` (it calls `LsaStorePrivateData`, like Sysinternals Autologon).

## Network and Remote Desktop

The VM is bridged, so it gets its own LAN address from the router. Reserve that address by the MAC in `ethernet0.generatedAddress`. `/etc/vmware/networking` has `add_bridge_mapping enp5s0 0`, but `vmnet-bridge` treats that only as a preference. When the wired port blipped (at boot, or when Wi-Fi was turned off), it moved `vmnet0` to `lerd0` and stayed there, leaving Windows on a `169.254` address with no network. `system/omarchy/etc/systemd/system/vmware-networks.service.d/pin-bridge.conf` runs `system/omarchy/usr/local/libexec/vmnet0-pin-bridge` after the service starts, which restarts the bridge with `-i <mapped interface>`. Both are installed by `scripts/bootstrap-omarchy --hardware`. `/proc/vmnet/bridge*` shows the interface in use. After a bad bridge, run `ipconfig /renew` in Windows (or `winvm cmd -c 'ipconfig /renew'`). The vmx then has no `ethernet0.connectionType` line, because bridged is the default. UFW on the host doesn't see bridged traffic, so Windows Firewall is the only filter.

Remote Desktop is on, with Network Level Authentication, and its three firewall rules are limited to `LocalSubnet`. Bridged Windows also takes public IPv6 addresses from the router, so rules open to `Any` would rely on the router to block inbound IPv6. The Windows App on macOS connects to the LAN address.

## Shared folders

VMware Shared Folders (in VMware Tools) expose two host folders to Windows, both writable:

| Host folder | Windows drive | Use |
| --- | --- | --- |
| `~/Documents/Windows-Bridge` | `Z:` | General exchange, such as Fusion exports for Bambu Studio |
| `~/Downloads/3D Printing` | `Y:` | Downloaded models |

Windows reaches them at `\\vmware-host\Shared Folders\<name>`. The "Map shared folders" scheduled task runs `docs/windows-vm/map-shares.ps1` (installed as `C:\ProgramData\SharedFolders\map-shares.ps1`) hidden at each sign-in, through `conhost --headless`. It waits for the shares, then maps any missing drive with `net use /persistent:yes` and logs failures to `%LOCALAPPDATA%\map-shares.log`. A plain `RunOnce` entry failed: it ran before the shares were up and left a console window open. Files written from Windows are owned by the user with group `root`.

Set VM Settings → Options → Shared Folders to "Always enabled". `vmrun enableSharedFolders` only enables them until the next power-off. Editing `isolation.tools.hgfs.disable` or the `pref.sharedFolder*` lines in `~/.vmware/preferences` by hand doesn't stick: VMware rewrites both at power-on, and Windows then gets `System error 64`.

Copy and paste of text works both ways through VMware Tools, on by default (VM Settings → Options → Guest Isolation). Move files through the shares rather than the clipboard or drag and drop, which run through XWayland on the host.

Add or remove a share while the VM runs with `vmrun -T ws addSharedFolder <vmx> <name> <host path>` (then `setSharedFolderState ... writable`) or `removeSharedFolder <vmx> <name>`.

## Fusion MCP server

Fusion's built-in MCP server (Preferences → General → API) is set to port 27183 in the VM, so it never clashes with Fusion's default 27182 on another machine. It listens on loopback inside Windows only, has no authentication and answers `403 Invalid Host header` unless the `Host` header is `127.0.0.1:27183` (the port must match too). Forwarding the port inside Windows (`netsh portproxy`) therefore fails, and clients reach it through SSH instead, at `http://127.0.0.1:27183/mcp` on every machine.

- `docs/windows-vm/setup-ssh.ps1` installs OpenSSH Server as a tunnel and nothing else: key-only sign-in, `PermitOpen 127.0.0.1:27183`, `ForceCommand exit`, keys marked `restrict,port-forwarding,permitopen=...`, and the firewall rule limited to `LocalSubnet`. It merges the public keys in `C:\Windows\Temp\fusion-mcp-keys.txt` into `administrators_authorized_keys`, so re-run it to add a machine. Change `$port` there if Fusion's port changes.
- The `fusion-mcp` packages (`packages/common/fusion-mcp`, plus `packages/omarchy/fusion-mcp` or `packages/macos/fusion-mcp`) aren't stowed by `scripts/apply-dotfiles`. Each machine listens on `127.0.0.1:27183` and starts one `ssh -W 127.0.0.1:27183 fusion-vm` per connection, through systemd socket activation or launchd's `inetdCompatibility`. Nothing runs while idle. With the VM off a connection closes after 3 seconds, the client shows the server as failed, and the failed connection units clean themselves up.
- `~/.config/fusion-mcp/ssh_config` is used with `-F`, so `~/.ssh/config` and the 1Password agent stay out of it. It uses its own key (`~/.ssh/fusion-vm_ed25519`, no passphrase, so connections never wait on an approval) and pins the VM's host key in `~/.config/fusion-mcp/known_hosts`. The untracked `~/.config/fusion-mcp/host.conf` holds the VM's IPv4 address (reserve it on the router) and Windows user. `FUSION-VM.local` resolves over mDNS too, but a lookup takes 10 seconds to fail while the VM is off.

Fusion must be open in the VM. It exposes `fusion_mcp_read`, `fusion_mcp_update`, `fusion_mcp_execute` and `fusion_mcp_electronics_read`, all acting on the active document. ChatGPT on the web can't use it: its connectors run on OpenAI's servers and need a public HTTPS URL. The ChatGPT app on the Mac can.

Set up a machine:

1. Stow the packages: `stow --dir packages/common --target ~ --no-folding fusion-mcp`, then the same with `--dir packages/omarchy` or `--dir packages/macos`.
2. Create the key: `ssh-keygen -t ed25519 -N '' -C "fusion-mcp@$(hostname -s)" -f ~/.ssh/fusion-vm_ed25519`.
3. Write `~/.config/fusion-mcp/host.conf` with `HostName <VM address>` and `User <Windows user>`, and copy `~/.config/fusion-mcp/known_hosts` from Omarchy (one line, `fusion-vm ssh-ed25519 ...`). For a rebuilt VM, make that line from the `C:\ProgramData\ssh\ssh_host_ed25519_key.pub` the script copies to `C:\Windows\Temp\`.
4. Add the key to the VM from Omarchy: copy the `.pub` file into the guest as `C:\Windows\Temp\fusion-mcp-keys.txt`, then copy and run `setup-ssh.ps1` as the comment at its top shows.
5. Start the listener:
   - Omarchy: `systemctl --user enable --now fusion-mcp.socket`
   - Mac: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.fusion-mcp.plist`
6. Register `http://127.0.0.1:27183/mcp`: `claude mcp add --scope user --transport http fusion <URL>` and `codex mcp add fusion --url <URL>`. Where `fusion` already means that machine's own Fusion (the Mac), name it `fusion-vm`. Claude Desktop's Autodesk Fusion extension takes the port, and the ChatGPT app takes the URL as a connector.

`systemctl --user disable` deletes the stowed unit links along with the enablement links. Re-stow afterwards, then run `systemctl --user daemon-reload`.

## Agent skill

The `windows-vm` skill teaches coding agents to control the VM, and `winvm` is its helper. The commands are:

- `status`
- `screenshot`
- `ps` (PowerShell)
- `cmd`
- `push` and `pull` (copy files)
- `launch` (a visible app)
- `processes`
- `start` and `stop`

The skill lives in `packages/omarchy/windows-vm/.agents/skills/windows-vm/`. The package links it into `~/.agents/skills` (Grok), `~/.claude/skills` and `~/.codex/skills`, and links `winvm` into `~/.local/bin`. `scripts/apply-dotfiles` doesn't stow it. Stow it on the machine that runs the VM:

```sh
stow --dir packages/omarchy --target ~ --no-folding windows-vm
```

`ps` and `cmd` copy a script into `C:\Windows\Temp`, run it through `cmd /c` with its output redirected to a file, copy the output back and delete both files. Each call takes about 4 seconds and returns the Windows exit code. PowerShell scripts are written with a UTF-8 BOM, since Windows PowerShell 5.1 reads a script without one as ANSI. `vmrun -gp` passes the password on the command line, so other local processes can see it in the process list while a guest command runs. Screenshots come from `vmcli <vmx> MKS captureScreenshot` and need no credentials. `runProgramInGuest -activateWindow` is rejected ("Invalid argument"), so `launch` uses `-interactive -noWait`.

## Start and stop

```sh
vmrun -T ws start ~/vmware/Fusion-Win11/Fusion-Win11.vmx gui
vmrun -T ws stop ~/vmware/Fusion-Win11/Fusion-Win11.vmx soft
```

## Rebuild the VM

`docs/windows-vm/` holds the VM config and an unattended install:

- `Fusion-Win11.vmx`: VMware doesn't expand `~`, so make the ISO paths absolute.
- `autounattend.xml.in`: Windows 11 Pro, en-AU with a US keyboard and an auto sign-in local admin account. Replace `@@USERNAME@@`, `@@PASSWORD@@` and `@@TIMEZONE@@` (a Windows time zone ID from `tzutil /l`).
- `firstlogon.ps1`: runs elevated at the first sign-in. It installs VMware Tools from `/usr/lib/vmware/isoimages/windows.iso`, runs `debloat.ps1` and `install-fusion.ps1`, then restarts.
- `debloat.ps1`: removes consumer apps, turns off Widgets, Copilot, search indexing, sleep and hibernation.
- `install-fusion.ps1`: downloads Autodesk's Fusion Client Downloader, installs it with `--globalinstall --quiet` only if its signature is Autodesk's, and logs to `C:\setup-log.txt`.

Steps:

1. Download the Windows 11 x64 ISO from Microsoft and check its SHA-256 against the list on the download page.
2. Create the disk: `vmware-vdiskmanager -c -s 128GB -a lsilogic -t 0 Fusion-Win11.vmdk`.
3. Generate a random password, save it to `~/vmware/Fusion-Win11/guest-password` (mode 600) and 1Password, save the user name to `guest-user` beside it, and fill in the answer file. Put `autounattend.xml` at the root of a disc image and the three scripts under `setup/`, then build it with `bsdtar --format iso9660 --options 'volume-id=UNATTEND,joliet,rockridge' -cf autounattend.iso -C <dir> .`.
4. Start the VM and press a key at "Press any key to boot from CD or DVD". The rest runs unattended.
5. Sign in to Fusion with the Autodesk account.
6. With the VM off, drop the install discs (keep one empty `sata0:0` with `startConnected = "FALSE"`), set `ethernet0.virtualDev = "vmxnet3"` and `bios.bootOrder = "hdd"`. The answer file and its disc hold the password in plain text, so delete them.

Guest commands from the host work with `vmrun -T ws -gu <user> -gp <password> runProgramInGuest`, and they run elevated. Wrap PowerShell in `cmd /c powershell ...`: launching `powershell.exe` directly exits with code 1 before the script runs.
