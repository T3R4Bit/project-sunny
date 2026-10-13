#!/usr/bin/env python3
"""Host status collector for Sunny's dashboard.

Runs on the M-700 as root (systemd `sunny-collector.service`, installed by deploy/install.sh) and
every INTERVAL seconds writes a JSON snapshot that the sunny container reads through a read-only
bind mount. Collecting on the host keeps the container unprivileged: it never gets the Tailscale
socket, the Docker socket, or systemd access.

Stdlib only. Every section is independent: one failing probe records an "error" and the rest
still report.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import struct
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(os.environ.get("SUNNY_STATUS_FILE", "/home/sunny/sunny-status/status.json"))
INTERVAL = int(os.environ.get("SUNNY_STATUS_INTERVAL", "20"))
HOST_USER = os.environ.get("SUNNY_HOST_USER", "sunny")
SUNNY_BACKUPS = Path(os.environ.get("SUNNY_BACKUP_DIR", "/home/sunny/sunny-backups"))
MC_BACKUPS = Path(os.environ.get("MC_BACKUP_DIR", "/home/sunny/minecraft-backups/snapshots"))
MC_ADDR = ("127.0.0.1", int(os.environ.get("MC_PORT", "25565")))

SYSTEM_UNITS = ["docker.service", "tailscaled.service", "sunny-backup.timer", "ssh.service", "fail2ban.service"]
USER_UNITS = ["minecraft.service", "playit.service", "minecraft-backup.timer"]


def run(*cmd: str, timeout: float = 10) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True).stdout


def iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None


# --- host ---------------------------------------------------------------------------------

_prev_cpu: tuple[int, int] | None = None


def _cpu_times() -> tuple[int, int]:
    fields = [int(x) for x in Path("/proc/stat").read_text().split("\n", 1)[0].split()[1:]]
    idle = fields[3] + fields[4]  # idle + iowait
    return idle, sum(fields)


def host() -> dict:
    global _prev_cpu
    idle, total = _cpu_times()
    cpu_pct = None
    if _prev_cpu and total > _prev_cpu[1]:
        cpu_pct = round(100 * (1 - (idle - _prev_cpu[0]) / (total - _prev_cpu[1])), 1)
    _prev_cpu = (idle, total)

    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        mem[k] = int(v.split()[0]) * 1024
    disk = shutil.disk_usage("/")
    load = [float(x) for x in Path("/proc/loadavg").read_text().split()[:3]]

    temps = []
    for zone in Path("/sys/class/hwmon").glob("hwmon*"):
        name = (zone / "name").read_text().strip() if (zone / "name").exists() else zone.name
        for t in zone.glob("temp*_input"):
            try:
                temps.append((name, int(t.read_text()) / 1000))
            except (OSError, ValueError):
                pass
    cpu_temps = [v for n, v in temps if n in ("coretemp", "k10temp", "zenpower", "cpu_thermal")]

    os_name = ""
    if Path("/etc/os-release").exists():
        m = re.search(r'^PRETTY_NAME="?([^"\n]+)', Path("/etc/os-release").read_text(), re.MULTILINE)
        os_name = m.group(1) if m else ""

    return {
        "hostname": socket.gethostname(),
        "os": os_name,
        "kernel": os.uname().release,
        "uptime_s": int(float(Path("/proc/uptime").read_text().split()[0])),
        "cpu_count": os.cpu_count(),
        "cpu_pct": cpu_pct,
        "load": load,
        "mem_total": mem.get("MemTotal"),
        "mem_available": mem.get("MemAvailable"),
        "swap_total": mem.get("SwapTotal"),
        "swap_free": mem.get("SwapFree"),
        "disk_total": disk.total,
        "disk_used": disk.used,
        "cpu_temp_c": round(max(cpu_temps), 1) if cpu_temps else (round(max(v for _, v in temps), 1) if temps else None),
    }


# --- tailscale ----------------------------------------------------------------------------


def tailscale() -> dict:
    data = json.loads(run("tailscale", "status", "--json"))
    users = {str(k): v.get("LoginName", "") for k, v in (data.get("User") or {}).items()}
    self_user = users.get(str(data["Self"].get("UserID")), "")

    def node(n: dict, is_self: bool = False) -> dict:
        dns = (n.get("DNSName") or "").rstrip(".")
        name = n.get("HostName", "")
        if not name or name == "localhost":  # iOS/Android report "localhost"; the MagicDNS label is the real name
            name = dns.split(".")[0] or name
        return {
            "name": name,
            "dns": dns,
            "os": n.get("OS", ""),
            "ip": (n.get("TailscaleIPs") or [""])[0],
            "online": bool(n.get("Online")) or is_self,
            "last_seen": None if is_self else n.get("LastSeen"),
            "direct": bool(n.get("CurAddr")),
            "relay": n.get("Relay", ""),
            "exit_node": bool(n.get("ExitNodeOption")),
            "owner": users.get(str(n.get("UserID")), ""),
            "shared": users.get(str(n.get("UserID")), self_user) != self_user,
            "rx": n.get("RxBytes", 0),
            "tx": n.get("TxBytes", 0),
            "self": is_self,
        }

    peers = [node(p) for p in (data.get("Peer") or {}).values()]
    peers.sort(key=lambda p: (not p["online"], p["name"].lower()))
    return {
        "tailnet": (data.get("CurrentTailnet") or {}).get("Name", ""),
        "version": data.get("Version", ""),
        "backend_state": data.get("BackendState", ""),
        "self": node(data["Self"], is_self=True),
        "peers": peers,
    }


# --- services -----------------------------------------------------------------------------


def _unit(name: str, user: bool) -> dict:
    cmd = ["systemctl"]
    if user:
        cmd += [f"--machine={HOST_USER}@", "--user"]
    props = "ActiveState,SubState,ActiveEnterTimestamp,Description,LastTriggerUSec,NextElapseUSecRealtime,Result"
    out = run(*cmd, "show", name, f"--property={props}")
    p = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return {
        "name": name.rsplit(".", 1)[0],
        "unit": name,
        "scope": "user" if user else "system",
        "description": p.get("Description", ""),
        "active": p.get("ActiveState", "unknown"),
        "sub": p.get("SubState", ""),
        "result": p.get("Result", ""),
        "since": p.get("ActiveEnterTimestamp") or None,
        "last_trigger": p.get("LastTriggerUSec") or None,
        "next": p.get("NextElapseUSecRealtime") or None,
    }


def services() -> list[dict]:
    out = []
    for name in SYSTEM_UNITS:
        try:
            out.append(_unit(name, user=False))
        except Exception as e:  # noqa: BLE001
            out.append({"name": name, "unit": name, "active": "unknown", "error": str(e)[:200]})
    for name in USER_UNITS:
        try:
            out.append(_unit(name, user=True))
        except Exception as e:  # noqa: BLE001
            out.append({"name": name, "unit": name, "active": "unknown", "error": str(e)[:200]})
    return out


def containers() -> list[dict]:
    rows = []
    for line in run("docker", "ps", "-a", "--format", "{{json .}}").splitlines():
        c = json.loads(line)
        rows.append({
            "name": c.get("Names", ""),
            "image": c.get("Image", ""),
            "state": c.get("State", ""),
            "status": c.get("Status", ""),
        })
    if rows:
        stats = {}
        for line in run("docker", "stats", "--no-stream", "--format", "{{json .}}", timeout=20).splitlines():
            s = json.loads(line)
            stats[s.get("Name")] = {"cpu": s.get("CPUPerc", ""), "mem": s.get("MemUsage", "")}
        for r in rows:
            r.update(stats.get(r["name"], {}))
    return rows


# --- syncthing ----------------------------------------------------------------------------


def syncthing() -> dict:
    cfg = run("docker", "exec", "syncthing", "sh", "-c",
              "cat /var/syncthing/config/config.xml 2>/dev/null || cat /var/syncthing/config.xml")
    key = re.search(r"<apikey>([^<]+)</apikey>", cfg).group(1)
    names = dict(re.findall(r'<device id="([A-Z0-9-]+)" name="([^"]*)"', cfg))

    def get(path: str) -> dict:
        req = urllib.request.Request("http://127.0.0.1:8384" + path, headers={"X-API-Key": key})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.load(r)

    conns = get("/rest/system/connections").get("connections", {})
    folders = []
    for fid in re.findall(r'<folder id="([^"]+)"', cfg):
        s = get(f"/rest/db/status?folder={fid}")
        folders.append({
            "id": fid, "state": s.get("state"), "files": s.get("globalFiles"),
            "need": s.get("needFiles", 0), "errors": s.get("errors", 0),
            "bytes": s.get("globalBytes"),
        })
    return {
        "devices": [{"name": names.get(d, d[:7]), "connected": c.get("connected", False), "address": c.get("address", "")}
                    for d, c in conns.items()],
        "folders": folders,
    }


# --- minecraft (Server List Ping) ---------------------------------------------------------


def _varint(n: int) -> bytes:
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def _read_varint(sock: socket.socket) -> int:
    n = shift = 0
    while True:
        b = sock.recv(1)
        if not b:
            raise ConnectionError("closed")
        n |= (b[0] & 0x7F) << shift
        if not b[0] & 0x80:
            return n
        shift += 7


def minecraft() -> dict:
    start = time.monotonic()
    with socket.create_connection(MC_ADDR, timeout=3) as s:
        host = MC_ADDR[0].encode()
        handshake = b"\x00" + _varint(767) + _varint(len(host)) + host + struct.pack(">H", MC_ADDR[1]) + _varint(1)
        s.sendall(_varint(len(handshake)) + handshake)
        s.sendall(b"\x01\x00")
        _read_varint(s)  # packet length
        _read_varint(s)  # packet id
        length = _read_varint(s)
        buf = b""
        while len(buf) < length:
            chunk = s.recv(length - len(buf))
            if not chunk:
                break
            buf += chunk
    data = json.loads(buf)
    desc = data.get("description", "")
    if isinstance(desc, dict):
        desc = desc.get("text", "") + "".join(e.get("text", "") for e in desc.get("extra", []) if isinstance(e, dict))
    players = data.get("players", {})
    return {
        "online": True,
        "version": (data.get("version") or {}).get("name", ""),
        "players": players.get("online", 0),
        "max": players.get("max", 0),
        "names": [p.get("name") for p in players.get("sample", []) or []],
        "motd": re.sub(r"§.", "", desc or "").strip(),
        "latency_ms": round((time.monotonic() - start) * 1000),
    }


# --- backups ------------------------------------------------------------------------------


def _latest(directory: Path, pattern: str) -> dict | None:
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime) if directory.exists() else []
    if not files:
        return None
    f = files[-1]
    size = f.stat().st_size if f.is_file() else None
    return {"name": f.name, "time": iso(f.stat().st_mtime), "size": size, "count": len(files)}


def backups() -> dict:
    return {"sunny": _latest(SUNNY_BACKUPS, "sunny-*.tar.gz"), "minecraft": _latest(MC_BACKUPS, "*")}


# --- main ---------------------------------------------------------------------------------


def collect() -> dict:
    snap: dict = {"collected_at": datetime.now(timezone.utc).isoformat(), "interval_s": INTERVAL}
    for key, fn in (("host", host), ("tailscale", tailscale), ("services", services), ("containers", containers),
                    ("syncthing", syncthing), ("minecraft", minecraft), ("backups", backups)):
        try:
            snap[key] = fn()
        except Exception as e:  # noqa: BLE001 — one bad probe must not blank the dashboard
            snap[key] = {"error": f"{type(e).__name__}: {e}"[:300]}
    if "error" in snap.get("minecraft", {}):
        snap["minecraft"]["online"] = False
    return snap


def write(snap: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, indent=1))
    os.chmod(tmp, 0o644)
    os.replace(tmp, OUT)


if __name__ == "__main__":
    host()  # prime the CPU counters so the first snapshot has a real cpu_pct
    time.sleep(1)
    while True:
        write(collect())
        time.sleep(INTERVAL)
