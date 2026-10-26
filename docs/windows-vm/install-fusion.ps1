# Downloads Autodesk's Fusion installer, checks its Autodesk code signature and
# installs Fusion for all users without prompts. Logs to C:\setup-log.txt.
$ErrorActionPreference = 'Stop'
$log = 'C:\setup-log.txt'
function Log($msg) { "$(Get-Date -Format s) $msg" | Out-File -Append -Encoding utf8 $log }

$url = 'https://dl.appstreaming.autodesk.com/production/installers/Fusion%20Client%20Downloader.exe'
$exe = 'C:\Windows\Temp\FusionClientDownloader.exe'

Log 'Downloading Fusion installer'
$ProgressPreference = 'SilentlyContinue'
Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
Log "Downloaded $((Get-Item $exe).Length) bytes, SHA256 $((Get-FileHash $exe).Hash)"

$sig = Get-AuthenticodeSignature $exe
Log "Signature: $($sig.Status), signer: $($sig.SignerCertificate.Subject)"
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'O="?Autodesk, Inc.') {
  Log 'Signature check failed, not installing'
  return
}

Log 'Installing Fusion'
$p = Start-Process $exe -ArgumentList '--globalinstall --quiet' -Wait -PassThru
Log "Fusion installer exit code $($p.ExitCode)"
Log "Fusion install step done"
