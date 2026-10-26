# Turns on automatic sign-in for the account running this script. Reads the
# password from C:\Windows\Temp\pw.txt (copied from the host's guest-password
# file), deletes that file, and stores the password as the LSA secret
# "DefaultPassword", like Sysinternals Autologon. Run elevated, for example:
#   vmrun -T ws -gu <user> -gp <password> CopyFileFromHostToGuest <vmx> ~/vmware/Fusion-Win11/guest-password 'C:\Windows\Temp\pw.txt'
#   vmrun -T ws -gu <user> -gp <password> runProgramInGuest <vmx> 'C:\Windows\System32\cmd.exe' '/c powershell -NoProfile -ExecutionPolicy Bypass -File C:\Windows\Temp\set-autologon.ps1'
$pwFile = 'C:\Windows\Temp\pw.txt'
$o = 'C:\Windows\Temp\set-autologon.txt'
$pw = (Get-Content $pwFile -Raw).Trim()
Remove-Item $pwFile -Force
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Lsa {
  [StructLayout(LayoutKind.Sequential)] public struct UStr { public UInt16 Length; public UInt16 MaximumLength; public IntPtr Buffer; }
  [StructLayout(LayoutKind.Sequential)] public struct Attrs { public int Length; public IntPtr RootDirectory; public IntPtr ObjectName; public int Attributes; public IntPtr SecurityDescriptor; public IntPtr SecurityQualityOfService; }
  [DllImport("advapi32.dll")] static extern uint LsaOpenPolicy(IntPtr s, ref Attrs a, int access, out IntPtr h);
  [DllImport("advapi32.dll")] static extern uint LsaStorePrivateData(IntPtr h, ref UStr key, ref UStr data);
  [DllImport("advapi32.dll")] static extern uint LsaClose(IntPtr h);
  [DllImport("advapi32.dll")] static extern int LsaNtStatusToWinError(uint s);
  static UStr Make(string s) { var u = new UStr(); u.Buffer = Marshal.StringToHGlobalUni(s); u.Length = (UInt16)(s.Length * 2); u.MaximumLength = (UInt16)(u.Length + 2); return u; }
  public static int Store(string key, string value) {
    var a = new Attrs(); IntPtr h;
    uint st = LsaOpenPolicy(IntPtr.Zero, ref a, 0x000F0FFF, out h);
    if (st != 0) return LsaNtStatusToWinError(st);
    var k = Make(key); var d = Make(value);
    st = LsaStorePrivateData(h, ref k, ref d);
    Marshal.FreeHGlobal(k.Buffer); Marshal.FreeHGlobal(d.Buffer); LsaClose(h);
    return LsaNtStatusToWinError(st);
  }
}
'@
$err = [Lsa]::Store('DefaultPassword', $pw)
$pw = $null
$w = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
Set-ItemProperty $w -Name AutoAdminLogon -Value '1' -Type String
Set-ItemProperty $w -Name DefaultUserName -Value $env:USERNAME -Type String
Set-ItemProperty $w -Name DefaultDomainName -Value $env:COMPUTERNAME -Type String
Remove-ItemProperty $w -Name DefaultPassword -ErrorAction SilentlyContinue
Remove-ItemProperty $w -Name AutoLogonCount -ErrorAction SilentlyContinue
$r = Get-ItemProperty $w
"lsa store result: $err; AutoAdminLogon=$($r.AutoAdminLogon) DefaultUserName=$($r.DefaultUserName) DefaultDomainName=$($r.DefaultDomainName)" | Out-File $o -Encoding utf8
