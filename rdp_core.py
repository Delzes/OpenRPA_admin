from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000

WTS_CURRENT_SERVER_HANDLE = 0
WTSUserName = 5
WTSDomainName = 7

WTS_STATE = {
    0: "Active",
    1: "Connected",
    2: "ConnectQuery",
    3: "Shadow",
    4: "Disconnected",
    5: "Idle",
    6: "Listen",
    7: "Reset",
    8: "Down",
    9: "Init",
}

wtsapi = ctypes.WinDLL("wtsapi32", use_last_error=True)
crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class WTS_SESSION_INFOW(ctypes.Structure):
    _fields_ = [
        ("SessionId", wintypes.DWORD),
        ("pWinStationName", wintypes.LPWSTR),
        ("State", wintypes.DWORD),
    ]


PWTS_SESSION_INFOW = ctypes.POINTER(WTS_SESSION_INFOW)

wtsapi.WTSOpenServerW.argtypes = [wintypes.LPWSTR]
wtsapi.WTSOpenServerW.restype = wintypes.HANDLE
wtsapi.WTSCloseServer.argtypes = [wintypes.HANDLE]
wtsapi.WTSCloseServer.restype = None
wtsapi.WTSEnumerateSessionsW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(PWTS_SESSION_INFOW),
    ctypes.POINTER(wintypes.DWORD),
]
wtsapi.WTSEnumerateSessionsW.restype = wintypes.BOOL
wtsapi.WTSQuerySessionInformationW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(wintypes.DWORD),
]
wtsapi.WTSQuerySessionInformationW.restype = wintypes.BOOL
wtsapi.WTSFreeMemory.argtypes = [ctypes.c_void_p]
wtsapi.WTSFreeMemory.restype = None

crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    wintypes.LPCWSTR,
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
crypt32.CryptProtectData.restype = wintypes.BOOL
kernel32.LocalFree.argtypes = [ctypes.c_void_p]
kernel32.LocalFree.restype = ctypes.c_void_p


@dataclass
class Settings:
    fullscreen: bool = True
    multimon: bool = False
    no_consent_prompt: bool = True
    connect_delay_ms: int = 450
    prompt_for_credentials: bool = False


@dataclass
class Account:
    name: str
    machine: str
    username: str
    password: str
    enabled: bool = True
    port: int | None = None

    @property
    def host(self) -> str:
        return split_host_port(self.machine)[0]

    @property
    def rdp_address(self) -> str:
        host, parsed_port = split_host_port(self.machine)
        port = self.port or parsed_port
        return f"{host}:{port}" if port else host

    @property
    def short_user(self) -> str:
        return self.username.replace("/", "\\").split("\\")[-1]

    @property
    def domain(self) -> str:
        parts = self.username.replace("/", "\\").split("\\", 1)
        return parts[0] if len(parts) == 2 else ""

    @property
    def key(self) -> str:
        return f"{self.rdp_address}|{self.username.lower()}"


@dataclass
class SessionInfo:
    session_id: int
    username: str
    domain: str
    state: int
    station: str

    @property
    def state_name(self) -> str:
        return WTS_STATE.get(self.state, str(self.state))

    @property
    def display_user(self) -> str:
        if self.domain:
            return f"{self.domain}\\{self.username}"
        return self.username


@dataclass
class AppData:
    settings: Settings
    accounts: list[Account]
    source: Path
    comment: str = ""


@dataclass
class CacheClearResult:
    files: int = 0
    registry_keys: int = 0
    credentials: int = 0
    errors: list[str] = field(default_factory=list)


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def accounts_path() -> Path:
    return app_dir() / "accounts.json"


def split_host_port(machine: str) -> tuple[str, int | None]:
    value = (machine or "").strip()
    if value.startswith("[") and "]" in value:
        host, rest = value[1:].split("]", 1)
        if rest.startswith(":") and rest[1:].isdigit():
            return host, int(rest[1:])
        return host, None
    if value.count(":") == 1:
        host, port = value.rsplit(":", 1)
        if port.isdigit():
            return host, int(port)
    return value, None


def load_accounts(path: Path | None = None) -> AppData:
    path = path or accounts_path()
    if not path.exists():
        raise FileNotFoundError(f"Не найден файл учёток: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    settings_raw = raw.get("settings") or {}
    settings = Settings(
        fullscreen=bool(settings_raw.get("fullscreen", True)),
        multimon=bool(settings_raw.get("multimon", False)),
        no_consent_prompt=bool(settings_raw.get("no_consent_prompt", True)),
        connect_delay_ms=int(settings_raw.get("connect_delay_ms", 450)),
        prompt_for_credentials=bool(settings_raw.get("prompt_for_credentials", False)),
    )
    accounts: list[Account] = []
    for item in raw.get("accounts") or []:
        username = str(item.get("username") or item.get("login") or "").strip()
        machine = str(item.get("machine") or item.get("host") or "").strip()
        if not username or not machine:
            continue
        port = item.get("port")
        accounts.append(
            Account(
                name=str(item.get("name") or item.get("title") or username.split("\\")[-1]),
                machine=machine,
                username=username,
                password=str(item.get("password") or ""),
                enabled=bool(item.get("enabled", True)),
                port=int(port) if port not in (None, "") else None,
            )
        )
    return AppData(
        settings=settings,
        accounts=accounts,
        source=path,
        comment=str(raw.get("_comment") or ""),
    )


def _run(args: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="oem",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )


def _crypt_protect(data: bytes, description: str = "psw") -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        description,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def encrypt_rdp_password(password: str) -> str:
    payload = password.encode("utf-16-le") + b"\x00\x00"
    return _crypt_protect(payload).hex()


def store_rdp_credential(host: str, username: str, password: str) -> None:
    result = _run(
        [
            "cmdkey",
            f"/generic:TERMSRV/{host}",
            f"/user:{username}",
            f"/pass:{password}",
        ]
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "cmdkey error").strip()
        raise RuntimeError(message)


def delete_rdp_credential(host: str) -> bool:
    result = _run(["cmdkey", f"/delete:TERMSRV/{host}"])
    return result.returncode == 0


def write_rdp_file(account: Account, settings: Settings, extra: dict[str, str] | None = None) -> Path:
    lines = {
        "screen mode id:i": "2" if settings.fullscreen else "1",
        "use multimon:i": "1" if settings.multimon else "0",
        "session bpp:i": "32",
        "compression:i": "1",
        "keyboardhook:i": "2",
        "audiomode:i": "2",
        "redirectprinters:i": "0",
        "redirectcomports:i": "0",
        "redirectsmartcards:i": "0",
        "redirectclipboard:i": "1",
        "autoreconnection enabled:i": "1",
        "authentication level:i": "2",
        "prompt for credentials:i": "1" if settings.prompt_for_credentials else "0",
        "negotiate security layer:i": "1",
        "disable wallpaper:i": "1",
        "allow font smoothing:i": "0",
        "bitmapcachepersistenable:i": "1",
        "full address:s": account.rdp_address,
        "username:s": account.username,
    }
    if account.domain:
        lines["domain:s"] = account.domain
    if account.password and not settings.prompt_for_credentials:
        lines["password 51:b"] = encrypt_rdp_password(account.password)
    if extra:
        lines.update(extra)
    handle = tempfile.NamedTemporaryFile(
        prefix="openrpa_",
        suffix=".rdp",
        delete=False,
        mode="w",
        encoding="utf-8",
    )
    with handle as fh:
        for key, value in lines.items():
            fh.write(f"{key}:{value}\n")
    return Path(handle.name)


def launch_mstsc(args: list[str]) -> None:
    subprocess.Popen(
        ["mstsc", *args],
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
    )


def connect_rdp(account: Account, settings: Settings) -> None:
    if account.password:
        store_rdp_credential(account.host, account.username, account.password)
    rdp_path = write_rdp_file(account, settings)
    args = [str(rdp_path)]
    if settings.fullscreen:
        args.append("/f")
    launch_mstsc(args)


def _query_session_string(server, session_id: int, info_class: int) -> str:
    buffer = ctypes.c_void_p()
    length = wintypes.DWORD()
    ok = wtsapi.WTSQuerySessionInformationW(
        server,
        session_id,
        info_class,
        ctypes.byref(buffer),
        ctypes.byref(length),
    )
    if not ok or not buffer.value:
        return ""
    try:
        return ctypes.wstring_at(buffer) or ""
    finally:
        wtsapi.WTSFreeMemory(buffer)


def enumerate_sessions(host: str) -> list[SessionInfo]:
    handle = wtsapi.WTSOpenServerW(host)
    if not handle:
        raise RuntimeError(f"Не удалось открыть сервер {host}. Нужны права на удалённый рабочий стол.")
    try:
        pp_info = PWTS_SESSION_INFOW()
        count = wintypes.DWORD()
        if not wtsapi.WTSEnumerateSessionsW(handle, 0, 1, ctypes.byref(pp_info), ctypes.byref(count)):
            raise ctypes.WinError(ctypes.get_last_error())
        sessions: list[SessionInfo] = []
        try:
            for i in range(count.value):
                info = pp_info[i]
                if info.SessionId == 0:
                    continue
                username = _query_session_string(handle, info.SessionId, WTSUserName).strip()
                domain = _query_session_string(handle, info.SessionId, WTSDomainName).strip()
                station = info.pWinStationName or ""
                sessions.append(
                    SessionInfo(
                        session_id=int(info.SessionId),
                        username=username,
                        domain=domain,
                        state=int(info.State),
                        station=station,
                    )
                )
        finally:
            wtsapi.WTSFreeMemory(pp_info)
        return sessions
    finally:
        wtsapi.WTSCloseServer(handle)


def _parse_qwinsta(output: str) -> list[SessionInfo]:
    sessions: list[SessionInfo] = []
    for line in output.splitlines()[1:]:
        match = re.search(
            r"(\d+)\s+(Active|Conn(?:ected)?|Disc(?:onnected)?|Listen|Idle|Shadow|Актив|Диск|Слуш|Прост)",
            line,
            re.IGNORECASE,
        )
        if not match:
            continue
        session_id = int(match.group(1))
        if session_id == 0:
            continue
        state_raw = match.group(2).lower()
        state = 0
        if state_raw.startswith(("disc", "диск")):
            state = 4
        elif state_raw.startswith(("listen", "слуш")):
            state = 6
        elif state_raw.startswith(("idle", "прост")):
            state = 5
        elif state_raw.startswith("shadow"):
            state = 3
        left = line[: match.start()].strip()
        parts = left.split()
        username = ""
        station = ""
        if len(parts) == 1:
            token = parts[0]
            if re.search(r"rdp|console|services|#", token, re.I):
                station = token
            else:
                username = token
        elif len(parts) >= 2:
            station = parts[0]
            username = parts[-1]
        sessions.append(
            SessionInfo(
                session_id=session_id,
                username=username,
                domain="",
                state=state,
                station=station,
            )
        )
    return sessions


def list_sessions(host: str) -> list[SessionInfo]:
    try:
        return enumerate_sessions(host)
    except Exception:
        result = _run(["qwinsta", f"/server:{host}"], timeout=15)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "qwinsta error").strip()
            raise RuntimeError(f"Не удалось получить сессии {host}: {detail}") from None
        parsed = _parse_qwinsta(result.stdout or "")
        if not parsed and (result.stdout or result.stderr):
            raise RuntimeError(
                f"Не удалось разобрать список сессий {host}.\n{(result.stdout or result.stderr).strip()}"
            )
        return parsed


def _user_matches(session: SessionInfo, account: Account) -> bool:
    want_user = account.short_user.lower()
    want_full = account.username.replace("/", "\\").lower()
    got_user = session.username.lower()
    got_full = session.display_user.replace("/", "\\").lower()
    return got_user == want_user or got_full == want_full or got_full.endswith("\\" + want_user)


def find_session(account: Account) -> SessionInfo:
    sessions = [item for item in list_sessions(account.host) if item.username]
    matches = [item for item in sessions if _user_matches(item, account)]
    if not matches:
        names = ", ".join(item.display_user or f"#{item.session_id}" for item in sessions) or "нет активных"
        raise RuntimeError(
            f"Сессия {account.username} не найдена на {account.host}. Сейчас: {names}"
        )
    for preferred in (0, 1, 4, 5, 3):
        for item in matches:
            if item.state == preferred:
                return item
    return matches[0]


def connect_shadow(account: Account, settings: Settings, control: bool = False) -> SessionInfo:
    session = find_session(account)
    if account.password:
        store_rdp_credential(account.host, account.username, account.password)
    args = [f"/v:{account.rdp_address}", f"/shadow:{session.session_id}"]
    if control:
        args.append("/control")
    if settings.no_consent_prompt:
        args.append("/noConsentPrompt")
    launch_mstsc(args)
    return session


def _delete_tree_files(path: Path) -> int:
    if not path.exists():
        return 0
    removed = 0
    if path.is_file():
        path.unlink(missing_ok=True)
        return 1
    for child in path.rglob("*"):
        if child.is_file() or child.is_symlink():
            try:
                child.unlink()
                removed += 1
            except OSError:
                continue
    return removed


def _list_termsrv_targets() -> list[str]:
    result = _run(["cmdkey", "/list"])
    text = result.stdout or ""
    targets: list[str] = []
    for match in re.finditer(r"Target:\s*(?:LegacyGeneric:\s*target=)?(TERMSRV/.+)", text, re.I):
        targets.append(match.group(1).strip())
    return targets


def clear_rdp_cache() -> CacheClearResult:
    result = CacheClearResult()
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    user = Path(os.environ.get("USERPROFILE", ""))
    cache_roots = [
        local / "Microsoft" / "Terminal Server Client" / "Cache",
    ]
    extra_files = [
        user / "Documents" / "Default.rdp",
        Path(os.environ.get("USERPROFILE", "")) / "Default.rdp",
    ]
    for root in cache_roots:
        try:
            result.files += _delete_tree_files(root)
            if root.name == "Cache":
                root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            result.errors.append(str(exc))
    for item in extra_files:
        try:
            if item.exists():
                item.unlink()
                result.files += 1
        except OSError as exc:
            result.errors.append(str(exc))

    try:
        import winreg

        with winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER) as hive:
            tsc = winreg.OpenKey(hive, r"Software\Microsoft\Terminal Server Client")
            try:
                for name in ("Default", "LocalDevices"):
                    try:
                        key = winreg.OpenKey(tsc, name, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
                    except FileNotFoundError:
                        continue
                    with key:
                        index = 0
                        values: list[str] = []
                        while True:
                            try:
                                value_name, _, _ = winreg.EnumValue(key, index)
                                values.append(value_name)
                                index += 1
                            except OSError:
                                break
                        for value_name in values:
                            try:
                                winreg.DeleteValue(key, value_name)
                                result.registry_keys += 1
                            except OSError:
                                pass
                try:
                    servers = winreg.OpenKey(tsc, "Servers", 0, winreg.KEY_ALL_ACCESS)
                except FileNotFoundError:
                    servers = None
                if servers is not None:
                    with servers:
                        subkeys: list[str] = []
                        index = 0
                        while True:
                            try:
                                subkeys.append(winreg.EnumKey(servers, index))
                                index += 1
                            except OSError:
                                break
                        for sub in subkeys:
                            try:
                                winreg.DeleteKey(servers, sub)
                                result.registry_keys += 1
                            except OSError as exc:
                                result.errors.append(f"Servers\\{sub}: {exc}")
            finally:
                tsc.Close()
    except OSError as exc:
        result.errors.append(str(exc))

    for target in _list_termsrv_targets():
        deleted = _run(["cmdkey", f"/delete:{target}"])
        if deleted.returncode == 0:
            result.credentials += 1
        else:
            result.errors.append((deleted.stderr or deleted.stdout or target).strip())
    return result


def delay_seconds(settings: Settings) -> float:
    return max(0, settings.connect_delay_ms) / 1000.0


def staggered_pause(settings: Settings) -> None:
    wait = delay_seconds(settings)
    if wait:
        time.sleep(wait)
