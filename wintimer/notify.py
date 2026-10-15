"""Windows 系统通知（Toast）。

Win32 桌面程序要显示 Toast，需要有一个带 AppUserModelID 的开始菜单快捷方式。
本模块负责：
  1. 首次运行时写入带 AUMID 的开始菜单快捷方式；
  2. 调用 PowerShell 的 WinRT 接口弹出通知；
  3. 失败时如实上报，由界面决定是否退回自绘提醒窗。
"""

import os
import subprocess
import sys
from pathlib import Path

from . import APP_ID, APP_NAME
from .settings import config_dir

CREATE_NO_WINDOW = 0x08000000
POWERSHELL_AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
TOAST_SOUND = "ms-winsoundevent:Notification.Looping.Alarm2"


def powershell_exe() -> str:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if candidate.exists():
        return str(candidate)
    return "powershell.exe"


def start_menu_dir() -> Path:
    appdata = os.environ.get("APPDATA") or ""
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def shortcut_path() -> Path:
    return start_menu_dir() / f"{APP_NAME}.lnk"


def _ps_literal(text: str) -> str:
    """转成 PowerShell 单引号字符串字面量。"""
    return "'" + str(text).replace("'", "''") + "'"


def _run_ps(script: str, timeout: int = 30):
    """把脚本写盘后用文件重定向执行，返回 (returncode, stdout, stderr)。"""
    work = config_dir()
    script_path = work / "task.ps1"
    out_path = work / "task.out"
    err_path = work / "task.err"
    try:
        with open(script_path, "w", encoding="utf-8-sig") as fh:
            fh.write(script)
    except OSError as exc:
        return -1, "", f"write script failed: {exc}"
    try:
        with open(out_path, "wb") as out, open(err_path, "wb") as err:
            proc = subprocess.run(
                [powershell_exe(), "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
                stdout=out,
                stderr=err,
                timeout=timeout,
                creationflags=CREATE_NO_WINDOW,
            )
        code = proc.returncode
    except subprocess.TimeoutExpired:
        return -2, "", "powershell timeout"
    except OSError as exc:
        return -1, "", f"launch failed: {exc}"

    def _read(path):
        try:
            data = path.read_bytes()
        except OSError:
            return ""
        for enc in ("utf-8-sig", "gbk", "utf-8"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", "replace")

    return code, _read(out_path), _read(err_path)


# ---------------------------------------------------------------- Toast

_TOAST_TEMPLATE = """$ErrorActionPreference = 'Stop'
$ok = $false
try {{
  [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
  $tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
  $texts = $tpl.GetElementsByTagName('text')
  $texts.Item(0).AppendChild($tpl.CreateTextNode({title})) | Out-Null
  $texts.Item(1).AppendChild($tpl.CreateTextNode({message})) | Out-Null
{audio}
  $toast = [Windows.UI.Notifications.ToastNotification]::new($tpl)
  $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier({aumid})
  $notifier.Show($toast)
  $ok = $true
  Write-Output 'TOAST-OK'
}} catch {{
  Write-Output ('TOAST-FAIL: ' + $_.Exception.Message)
}}
if (-not $ok) {{ exit 3 }}
"""


def _build_toast_script(title: str, message: str, aumid: str, sound: str | None) -> str:
    if sound:
        audio = (
            "$audio = $tpl.CreateElement('audio')\n"
            f"  $audio.SetAttribute('src', {_ps_literal(sound)})\n"
            "  $audio.SetAttribute('silent', 'false')\n"
            "  $tpl.DocumentElement.AppendChild($audio) | Out-Null"
        )
    else:
        audio = ""
    return _TOAST_TEMPLATE.format(
        title=_ps_literal(title),
        message=_ps_literal(message),
        audio=audio,
        aumid=_ps_literal(aumid),
    )


def show_toast(title: str, message: str, sound: str | None = TOAST_SOUND):
    """弹出系统通知。返回 (是否成功, 说明)。"""
    for aumid in (APP_ID, POWERSHELL_AUMID):
        code, out, err = _run_ps(_build_toast_script(title, message, aumid, sound), timeout=30)
        if code == 0 and "TOAST-OK" in out:
            return True, f"ok ({aumid.split(chr(92))[0]})"
        detail = (out.strip() or err.strip() or f"exit={code}").replace("\n", " ")[:300]
    return False, detail


# ------------------------------------------------------- 开始菜单快捷方式

_SHORTCUT_SCRIPT = r"""$ErrorActionPreference = 'Stop'
$code = @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

[ComImport, Guid("00021401-0000-0000-C000-000000000046")]
internal class ShellLinkCoClass { }

[ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IShellLinkW
{
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszFile, int cch, IntPtr pfd, uint fFlags);
    void GetIDList(out IntPtr ppidl);
    void SetIDList(IntPtr pidl);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszName, int cch);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszDir, int cch);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszArgs, int cch);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
    void GetHotkey(out short pwHotkey);
    void SetHotkey(short wHotkey);
    void GetShowCmd(out int piShowCmd);
    void SetShowCmd(int iShowCmd);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszIconPath, int cch, out int piIcon);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel, uint dwReserved);
    void Resolve(IntPtr hwnd, uint fFlags);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
}

[StructLayout(LayoutKind.Sequential)]
internal struct PropertyKey { public Guid fmtid; public uint pid; }

[StructLayout(LayoutKind.Explicit)]
internal struct PropVariant
{
    [FieldOffset(0)] public ushort vt;
    [FieldOffset(8)] public IntPtr pointerValue;
}

[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IPropertyStore
{
    void GetCount(out uint cProps);
    void GetAt(uint iProp, out PropertyKey pkey);
    void GetValue(ref PropertyKey key, out PropVariant pv);
    void SetValue(ref PropertyKey key, ref PropVariant pv);
    void Commit();
}

public static class ShortcutMaker
{
    public static void Create(string lnkPath, string target, string arguments, string workDir,
                              string description, string iconPath, string aumid)
    {
        var link = (IShellLinkW)(new ShellLinkCoClass());
        link.SetPath(target);
        if (!string.IsNullOrEmpty(arguments)) link.SetArguments(arguments);
        if (!string.IsNullOrEmpty(workDir)) link.SetWorkingDirectory(workDir);
        if (!string.IsNullOrEmpty(description)) link.SetDescription(description);
        if (!string.IsNullOrEmpty(iconPath)) link.SetIconLocation(iconPath, 0);

        if (!string.IsNullOrEmpty(aumid))
        {
            var key = new PropertyKey();
            key.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
            key.pid = 5;
            var pv = new PropVariant();
            pv.vt = 31;
            pv.pointerValue = Marshal.StringToCoTaskMemUni(aumid);
            try
            {
                var store = (IPropertyStore)link;
                store.SetValue(ref key, ref pv);
                store.Commit();
            }
            finally
            {
                Marshal.FreeCoTaskMem(pv.pointerValue);
            }
        }

        ((IPersistFile)link).Save(lnkPath, true);
        Marshal.ReleaseComObject(link);
    }
}
'@

Add-Type -TypeDefinition $code -Language CSharp | Out-Null
[ShortcutMaker]::Create(__LNK__, __TARGET__, __ARGS__, __WORKDIR__, __DESC__, __ICON__, __AUMID__)
if (Test-Path __LNK__) { Write-Output 'SHORTCUT-OK' } else { Write-Output 'SHORTCUT-FAIL'; exit 4 }
"""


def _icon_source() -> str:
    """快捷方式图标来源：打包后是 exe 本身，开发时用 assets/icon.ico。"""
    if getattr(sys, "frozen", False):
        return sys.executable
    root = Path(__file__).resolve().parent.parent
    icon = root / "assets" / "icon.ico"
    return str(icon) if icon.exists() else sys.executable


def _target_source() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return sys.executable


def create_shortcut(lnk_path, target, arguments="", workdir="", description="",
                    icon="", aumid=APP_ID) -> bool:
    """创建带 AppUserModelID 的快捷方式（.lnk）。

    AUMID 必须写进快捷方式，系统通知才会以本应用的名义显示。
    """
    lnk_path = Path(lnk_path)
    try:
        lnk_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    script = (
        _SHORTCUT_SCRIPT
        .replace("__LNK__", _ps_literal(str(lnk_path)))
        .replace("__TARGET__", _ps_literal(str(target)))
        .replace("__ARGS__", _ps_literal(arguments or ""))
        .replace("__WORKDIR__", _ps_literal(str(workdir or Path(target).parent)))
        .replace("__DESC__", _ps_literal(description or APP_NAME))
        .replace("__ICON__", _ps_literal(str(icon or target)))
        .replace("__AUMID__", _ps_literal(aumid or ""))
    )
    code, out, err = _run_ps(script, timeout=90)
    return code == 0 and "SHORTCUT-OK" in out


def register_shortcut() -> bool:
    """写开始菜单快捷方式并绑定 AUMID（系统通知显示为本应用名称所需）。"""
    return create_shortcut(
        shortcut_path(),
        _target_source(),
        description=APP_NAME,
        icon=_icon_source(),
        aumid=APP_ID,
    )


def ensure_shortcut(force: bool = False) -> bool:
    if not force and shortcut_path().exists():
        return True
    return register_shortcut()
