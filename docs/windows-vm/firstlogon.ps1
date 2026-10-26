# Runs once, elevated, at the first automatic sign-in. Installs VMware Tools
# (SVGA 3D driver, vmxnet3, guest operations), trims Windows, installs Fusion,
# then restarts. Logs to C:\setup-log.txt.
$log = 'C:\setup-log.txt'
function Log($msg) { "$(Get-Date -Format s) $msg" | Out-File -Append -Encoding utf8 $log }

Log 'First logon script started'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# Keep the VM awake during setup.
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0

$tools = Get-PSDrive -PSProvider FileSystem |
  Where-Object { Test-Path "$($_.Root)VMwareToolsUpgrader.exe" } |
  Select-Object -First 1
if ($tools) {
  Log "VMware Tools found on $($tools.Root)"
  $p = Start-Process "$($tools.Root)setup.exe" -ArgumentList '/S /v"/qn REBOOT=R ADDLOCAL=ALL"' -Wait -PassThru
  Log "VMware Tools installer exit code $($p.ExitCode)"
} else {
  Log 'VMware Tools disc not found'
}

try { & "$here\debloat.ps1" } catch { Log "Debloat error: $_" }

# Wait for the network before downloading Fusion.
for ($i = 0; $i -lt 60; $i++) {
  if (Test-NetConnection dl.appstreaming.autodesk.com -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue) { break }
  Start-Sleep 5
}
try { & "$here\install-fusion.ps1" } catch { Log "Fusion install error: $_" }

Log 'First logon script finished, restarting'
shutdown /r /t 10 /c "Setup finished"
