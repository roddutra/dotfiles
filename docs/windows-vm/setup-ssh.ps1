# Sets up OpenSSH Server as a tunnel to Fusion's MCP server and nothing else:
# key-only sign-in, forwarding limited to 127.0.0.1:$port (Fusion's MCP port,
# set in its preferences), no shell, and the firewall rule limited to the local
# subnet. Merges the public keys in
# C:\Windows\Temp\fusion-mcp-keys.txt (one per line), then deletes that file, so
# re-run it to add another machine. Run elevated, for example:
#   vmrun -T ws -gu <user> -gp <password> runProgramInGuest <vmx> 'C:\Windows\System32\cmd.exe' '/c powershell -NoProfile -ExecutionPolicy Bypass -File C:\Windows\Temp\setup-ssh.ps1'
$ErrorActionPreference = 'Stop'
$port = 27183
$log = 'C:\Windows\Temp\setup-ssh.txt'
function Log($m) { "$(Get-Date -Format s) $m" | Out-File $log -Append -Encoding utf8 }

try {
  $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server*'
  if ($cap.State -ne 'Installed') {
    Log "installing $($cap.Name)"
    Add-WindowsCapability -Online -Name $cap.Name | Out-Null
  }

  $ssh = "$env:ProgramData\ssh"
  $noBom = New-Object Text.UTF8Encoding $false
  # The first start creates the host keys.
  if (-not (Test-Path "$ssh\ssh_host_ed25519_key")) { Start-Service sshd; Stop-Service sshd }

  $config = @"
# Written by setup-ssh.ps1: a tunnel to Fusion's MCP server and nothing else.
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
AllowAgentForwarding no
AllowTcpForwarding local
PermitOpen 127.0.0.1:$port
X11Forwarding no
PermitTTY no
ForceCommand exit

Match Group administrators
       AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys
"@
  [IO.File]::WriteAllText("$ssh\sshd_config", $config.Replace("`r`n", "`n"), $noBom)

  $keysFile = "$ssh\administrators_authorized_keys"
  $prefix = "restrict,port-forwarding,permitopen=`"127.0.0.1:$port`" "
  # Re-apply the options to existing keys, so a port change reaches them too.
  $keys = @(if (Test-Path $keysFile) {
    Get-Content $keysFile | Where-Object { $_.Trim() } | ForEach-Object {
      if ($_ -match '((ssh|ecdsa|sk)-\S+\s+\S+.*)$') { $prefix + $Matches[1] } else { $_ }
    }
  })
  $incoming = 'C:\Windows\Temp\fusion-mcp-keys.txt'
  if (Test-Path $incoming) {
    foreach ($k in Get-Content $incoming) {
      $k = $k.Trim()
      if (-not $k) { continue }
      $blob = ($k -split '\s+')[1]
      if (-not ($keys | Where-Object { $_.Contains($blob) })) { $keys += $prefix + $k; Log "added key $(($k -split '\s+')[2])" }
    }
    Remove-Item $incoming -Force
  }
  [IO.File]::WriteAllLines($keysFile, [string[]]$keys, $noBom)
  icacls $keysFile /inheritance:r /grant '*S-1-5-32-544:F' /grant '*S-1-5-18:F' | Out-Null

  if (-not (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH SSH Server (sshd)' -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow | Out-Null
  }
  Set-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -Enabled True -Profile Any -RemoteAddress LocalSubnet

  Set-Service sshd -StartupType Automatic
  Restart-Service sshd
  Copy-Item "$ssh\ssh_host_ed25519_key.pub" 'C:\Windows\Temp\ssh_host_ed25519_key.pub' -Force
  Log "done: sshd $((Get-Service sshd).Status), $($keys.Count) key(s)"
} catch {
  Log "failed: $_"
  exit 1
}
