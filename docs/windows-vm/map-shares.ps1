# Maps the VMware shared folders to drive letters at sign-in. Runs hidden from
# the "Map shared folders" scheduled task; waits for the shares to appear first
# because VMware Tools can start after the user session.
$log = "$env:LOCALAPPDATA\map-shares.log"
$shares = @{ 'Z:' = 'Windows-Bridge'; 'Y:' = '3D Printing' }
$root = '\\vmware-host\Shared Folders'
for ($i = 0; $i -lt 30 -and -not (Test-Path "$root\Windows-Bridge"); $i++) { Start-Sleep 2 }
foreach ($drive in $shares.Keys) {
  if (Test-Path "$drive\") { continue }
  $out = cmd /c "net use $drive `"$root\$($shares[$drive])`" /persistent:yes 2>&1"
  "$(Get-Date -Format s) $drive $($shares[$drive]): $out" | Out-File -Append -Encoding utf8 $log
}
