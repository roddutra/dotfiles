# Trims Windows 11 for a single-purpose Fusion VM: removes consumer apps,
# turns off background features that cost CPU, disk or RAM, and keeps the VM
# awake. Run elevated. Logs to C:\setup-log.txt.
$log = 'C:\setup-log.txt'
function Log($msg) { "$(Get-Date -Format s) $msg" | Out-File -Append -Encoding utf8 $log }
Log 'Debloat started'

$apps = @(
  'Clipchamp.Clipchamp', 'Microsoft.BingNews', 'Microsoft.BingWeather', 'Microsoft.BingSearch',
  'Microsoft.Copilot', 'Microsoft.GamingApp', 'Microsoft.GetHelp', 'Microsoft.Getstarted',
  'Microsoft.MicrosoftOfficeHub', 'Microsoft.MicrosoftSolitaireCollection', 'Microsoft.MicrosoftStickyNotes',
  'Microsoft.OutlookForWindows', 'Microsoft.People', 'Microsoft.PowerAutomateDesktop', 'Microsoft.Todos',
  'Microsoft.WindowsAlarms', 'Microsoft.WindowsFeedbackHub', 'Microsoft.WindowsMaps',
  'Microsoft.WindowsSoundRecorder', 'Microsoft.Xbox.TCUI', 'Microsoft.XboxGameOverlay',
  'Microsoft.XboxGamingOverlay', 'Microsoft.XboxIdentityProvider', 'Microsoft.XboxSpeechToTextOverlay',
  'Microsoft.YourPhone', 'Microsoft.ZuneMusic', 'Microsoft.ZuneVideo', 'Microsoft.549981C3F5F10',
  'Microsoft.Windows.DevHome', 'MicrosoftCorporationII.MicrosoftFamily', 'MicrosoftTeams', 'MSTeams',
  'Microsoft.MicrosoftJournal', 'Microsoft.Edge.GameAssist'
)
foreach ($app in $apps) {
  Get-AppxProvisionedPackage -Online | Where-Object DisplayName -eq $app |
    ForEach-Object { Remove-AppxProvisionedPackage -Online -PackageName $_.PackageName -ErrorAction SilentlyContinue | Out-Null }
  Get-AppxPackage -AllUsers -Name $app |
    ForEach-Object { Remove-AppxPackage -AllUsers -Package $_.PackageFullName -ErrorAction SilentlyContinue }
}
Log 'Consumer apps removed'

function SetDword($path, $name, $value) {
  New-Item -Path $path -Force -ErrorAction SilentlyContinue | Out-Null
  New-ItemProperty -Path $path -Name $name -Value $value -PropertyType DWord -Force | Out-Null
}
# Consumer features, suggested apps and tips
SetDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableWindowsConsumerFeatures' 1
SetDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableSoftLanding' 1
# Widgets and Copilot
SetDword 'HKLM:\SOFTWARE\Policies\Microsoft\Dsh' 'AllowNewsAndInterests' 0
SetDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot' 'TurnOffWindowsCopilot' 1
SetDword 'HKCU:\Software\Policies\Microsoft\Windows\WindowsCopilot' 'TurnOffWindowsCopilot' 1
# Web results in Start search
SetDword 'HKCU:\Software\Policies\Microsoft\Windows\Explorer' 'DisableSearchBoxSuggestions' 1
# Diagnostic data at the minimum Pro allows
SetDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection' 'AllowTelemetry' 1
# Delivery Optimization: no peer-to-peer uploads
SetDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization' 'DODownloadMode' 0
# Background apps
SetDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy' 'LetAppsRunInBackground' 2
Log 'Policies set'

# File indexing costs idle CPU and disk; Start still finds apps without it.
Stop-Service WSearch -Force -ErrorAction SilentlyContinue
Set-Service WSearch -StartupType Disabled
Log 'Search indexing disabled'

# Power: high performance, never sleep, no hibernation file.
powercfg /setactive SCHEME_MIN
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0
powercfg /hibernate off
Log 'Power settings applied'

Log 'Debloat finished'
