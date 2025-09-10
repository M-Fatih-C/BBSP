# app/system_info.py
import os
import sys
import json
import platform
import shutil
import subprocess
from datetime import datetime, timedelta
from typing import Any, Dict, List

import psutil
from cpuinfo import get_cpu_info

def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def _run(cmd: List[str], timeout: int = 5) -> str:
    try:
        return subprocess.check_output(cmd, text=True, timeout=timeout, stderr=subprocess.STDOUT)
    except Exception:
        return ""

def _is_windows() -> bool:
    return platform.system() == "Windows"

def _read_json_if_exists(p: str) -> Any:
    try:
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                return json.load(f)
    except Exception:
        pass
    return None

def _maybe_meipass_path(rel: str) -> str:
    # Resolve resource in PyInstaller bundle
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(__file__)
    return os.path.join(base, rel)

# ---------------- OS ----------------
def get_os_info() -> Dict[str, Any]:
    u = platform.uname()
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time
    return {
        "system": u.system,
        "node": u.node,
        "release": u.release,
        "version": u.version,
        "machine": u.machine,
        "processor_string": u.processor,
        "boot_time": boot_time.isoformat(timespec="seconds"),
        "uptime_seconds": int(uptime.total_seconds()),
    }

# ---------------- CPU ----------------
def _cpu_cpuid_cacheline() -> int | None:
    # Try to get cache line size via CPUID (x86 only)
    try:
        import cpuid  # type: ignore
        regs = cpuid.CPUID(0x1).ebx  # bits 15..8 contain CLFLUSH line size * 8
        clflush_line_size = (regs >> 8) & 0xff
        if clflush_line_size:
            return int(clflush_line_size * 8)  # bytes
    except Exception:
        pass
    return None

def _cpu_linux_proc() -> Dict[str, Any]:
    out = {"stepping": None, "model": None, "family": None, "cache_size": None}
    try:
        with open("/proc/cpuinfo", "r") as f:
            txt = f.read()
        for line in txt.splitlines():
            if ":" not in line: continue
            k, v = [s.strip() for s in line.split(":", 1)]
            if k == "stepping":
                out["stepping"] = v
            elif k == "model":
                out["model"] = v
            elif k == "cpu family":
                out["family"] = v
            elif k == "cache size":
                out["cache_size"] = v  # e.g., "16384 KB"
    except Exception:
        pass
    return out

def _cpu_wmi() -> Dict[str, Any]:
    if not _is_windows():
        return {}
    try:
        import wmi  # type: ignore
        c = wmi.WMI()
        cpus = c.Win32_Processor()
        if not cpus:
            return {}
        p = cpus[0]
        # Map selected fields
        d = {
            "name": getattr(p, "Name", None),
            "manufacturer": getattr(p, "Manufacturer", None),
            "stepping": getattr(p, "Stepping", None),
            "revision": getattr(p, "Revision", None),
            "l2_cache_kb": getattr(p, "L2CacheSize", None),
            "l3_cache_kb": getattr(p, "L3CacheSize", None),
            "max_clock_mhz": getattr(p, "MaxClockSpeed", None),
            "ext_clock_mhz": getattr(p, "ExtClock", None),
        }
        # TDP is not standardized in WMI; leave None.
        return d
    except Exception:
        return {}

def get_cpu_info_detailed() -> Dict[str, Any]:
    base = get_cpu_info() or {}
    freq = psutil.cpu_freq()
    per_core = psutil.cpu_freq(percpu=True) or []
    os_extra: Dict[str, Any] = {}
    if _is_windows():
        os_extra = _cpu_wmi()
    else:
        os_extra = _cpu_linux_proc()

    cache_line = _cpu_cpuid_cacheline()

    return {
        "brand": base.get("brand_raw") or base.get("brand", ""),
        "arch": base.get("arch_string_raw"),
        "bits": base.get("bits"),
        "count_physical": psutil.cpu_count(logical=False),
        "count_logical": psutil.cpu_count(logical=True),
        "base_freq_mhz": getattr(freq, "min", None),
        "max_freq_mhz": getattr(freq, "max", None),
        "current_freq_mhz": getattr(freq, "current", None),
        "per_core_mhz": [round(c.current,2) if hasattr(c,"current") else None for c in per_core],
        "flags": sorted((base.get("flags") or [])[:64]),
        "l2_cache_size": base.get("l2_cache_size") or os_extra.get("l2_cache_kb"),
        "l3_cache_size": base.get("l3_cache_size") or os_extra.get("l3_cache_kb"),
        "vendor_id": base.get("vendor_id_raw") or base.get("vendor_id"),
        "hz_advertised": base.get("hz_advertised_friendly"),
        "hz_actual": base.get("hz_actual_friendly"),
        "stepping": os_extra.get("stepping") or base.get("stepping"),
        "revision": os_extra.get("revision"),
        "ext_clock_mhz": os_extra.get("ext_clock_mhz"),
        "cache_line_size_bytes": cache_line,
        "tdp_watts": None,  # Not reliable portably
    }

# ---------------- Memory ----------------
def _human_bytes(n: int) -> str:
    units = ["B","KB","MB","GB","TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units)-1:
        f /= 1024.0
        i += 1
    return f"{f:.2f} {units[i]}"

def _windows_ram_modules() -> List[Dict[str, Any]]:
    if not _is_windows():
        return []
    try:
        import wmi  # type: ignore
        c = wmi.WMI()
        arr = []
        for m in c.Win32_PhysicalMemory():
            arr.append({
                "capacity_bytes": int(getattr(m, "Capacity", 0) or 0),
                "speed_mhz": int(getattr(m, "Speed", 0) or 0) if getattr(m,"Speed",None) else None,
                "manufacturer": getattr(m, "Manufacturer", None),
                "part_number": getattr(m, "PartNumber", None),
                "serial": getattr(m, "SerialNumber", None),
                "bank": getattr(m, "BankLabel", None),
                "slot": getattr(m, "DeviceLocator", None),
            })
        return arr
    except Exception:
        return []

def _find_spd_json() -> str | None:
    # Try default report paths for Libre/OpenHardwareMonitor
    candidates = [
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "LibreHardwareMonitor", "LibreHardwareMonitorReport.json"),
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "OpenHardwareMonitor", "OpenHardwareMonitorReport.json"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    # Fallback: env var MINICPZU_SPD_JSON can override
    envp = os.environ.get("MINICPZU_SPD_JSON")
    if envp and os.path.isfile(envp):
        return envp
    return None

def _parse_spd_from_lhm(json_obj: Any) -> List[Dict[str, Any]]:
    # Very heuristic: look for "Memory" / "SPD" sections with timings
    out = []
    try:
        text = json.dumps(json_obj)
        # crude parse: find "tCL", "tRCD", "tRP", "tRAS", "tRC" numeric
        import re
        pattern = re.compile(r'"(tCL|tRCD|tRP|tRAS|tRC|Voltage|DRAM Frequency|XMP Profile)":\s*("?)([\d\.]+)\2', re.I)
        matches = pattern.findall(text)
        if matches:
            d = {}
            for k, _, v in matches:
                key = k.lower().replace(" ", "_")
                try:
                    d[key] = float(v)
                except ValueError:
                    d[key] = v
            out.append(d)
    except Exception:
        pass
    return out

def _parse_spd_from_decode_dimms(txt: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        cur = {}
        for line in txt.splitlines():
            l = line.strip()
            if not l: 
                if cur:
                    out.append(cur); cur = {}
                continue
            if ":" in l:
                k, v = [s.strip() for s in l.split(":", 1)]
                lk = k.lower()
                if "tCL" in k or lk in ("cas latency","tcl"):
                    cur["tcl"] = v
                elif "tRCD" in k:
                    cur["trcd"] = v
                elif "tRP" in k:
                    cur["trp"] = v
                elif "tRAS" in k:
                    cur["tras"] = v
                elif "tRC" in k:
                    cur["trc"] = v
                elif "Voltage" in k.lower():
                    cur["voltage"] = v
                elif "Speed" in k:
                    cur["speed"] = v
        if cur:
            out.append(cur)
    except Exception:
        pass
    return out

def get_memory_info_detailed(spd_json_path: str | None = None, decode_dimms_txt: str | None = None) -> Dict[str, Any]:
    vm = psutil.virtual_memory()
    mem = {
        "total": vm.total,
        "available": vm.available,
        "used": vm.used,
        "percent": vm.percent,
        "swap_total": psutil.swap_memory().total,
        "swap_used": psutil.swap_memory().used,
        "swap_percent": psutil.swap_memory().percent,
    }
    modules = _windows_ram_modules()
    if modules:
        mem["modules"] = modules

    # SPD (optional)
    spd: List[Dict[str, Any]] = []
    path = spd_json_path or _find_spd_json()
    if path:
        j = _read_json_if_exists(path)
        if j:
            spd = _parse_spd_from_lhm(j)
    elif decode_dimms_txt and os.path.isfile(decode_dimms_txt):
        try:
            with open(decode_dimms_txt, "r", encoding="utf-8", errors="ignore") as f:
                spd = _parse_spd_from_decode_dimms(f.read())
        except Exception:
            pass
    if spd:
        mem["spd"] = spd
    return mem

# ---------------- Motherboard/BIOS ----------------
def get_motherboard_bios_section() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if _is_windows():
        try:
            import wmi  # type: ignore
            c = wmi.WMI()
            board = c.Win32_BaseBoard()
            bios = c.Win32_BIOS()
            if board:
                b = board[0]
                out["motherboard"] = {
                    "Manufacturer": getattr(b, "Manufacturer", None),
                    "Product": getattr(b, "Product", None),
                    "SerialNumber": getattr(b, "SerialNumber", None),
                    "Version": getattr(b, "Version", None),
                }
            if bios:
                bi = bios[0]
                rd = getattr(bi, "ReleaseDate", None)
                rds = None
                if isinstance(rd, str) and len(rd) >= 8:
                    try:
                        from datetime import datetime
                        dt = datetime.strptime(rd[:14], "%Y%m%d%H%M%S")
                        rds = dt.isoformat(timespec="seconds")
                    except Exception:
                        rds = rd
                out["bios"] = {
                    "Manufacturer": getattr(bi, "Manufacturer", None),
                    "SMBIOSBIOSVersion": getattr(bi, "SMBIOSBIOSVersion", None),
                    "ReleaseDate": rds,
                    "Version": getattr(bi, "Version", None),
                }
        except Exception:
            pass
    else:
        # Linux best-effort via dmidecode
        if _which("dmidecode"):
            raw = _run(["sudo","dmidecode","-t","baseboard","-t","bios"], timeout=6)
            if raw:
                out["raw_dmidecode"] = raw
    return out

# ---------------- GPU ----------------
def _gpu_gputil() -> List[Dict[str, Any]]:
    arr: List[Dict[str, Any]] = []
    try:
        import GPUtil  # type: ignore
        for g in GPUtil.getGPUs():
            arr.append({
                "name": g.name,
                "driver": getattr(g, "driver", None),
                "memory_total": int(getattr(g, "memoryTotal", 0) * 1024 * 1024),
                "memory_used": int(getattr(g, "memoryUsed", 0) * 1024 * 1024),
                "load_percent": int(getattr(g, "load", 0) * 100),
                "temperature_c": getattr(g, "temperature", None),
                "uuid": getattr(g, "uuid", None),
            })
    except Exception:
        pass
    return arr

def _gpu_nvidia_smi() -> List[Dict[str, Any]]:
    if not _which("nvidia-smi"):
        return []
    q = "name,driver_version,memory.total,memory.used,temperature.gpu,power.draw,fan.speed,clocks.gr,clocks.mem"
    out = _run(["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"], timeout=5)
    arr: List[Dict[str, Any]] = []
    if out:
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 9:
                arr.append({
                    "name": parts[0],
                    "driver": parts[1],
                    "memory_total_mb": int(parts[2]),
                    "memory_used_mb": int(parts[3]),
                    "temperature_c": _to_int(parts[4]),
                    "power_w": _to_float(parts[5]),
                    "fan_percent": _to_int(parts[6].replace("%","")) if "%" in parts[6] else _to_int(parts[6]),
                    "clock_graphics_mhz": _to_int(parts[7]),
                    "clock_mem_mhz": _to_int(parts[8]),
                    "source": "nvidia-smi"
                })
    return arr

def _to_int(x):
    try: return int(float(x))
    except: return None

def _to_float(x):
    try: return float(x)
    except: return None

def _gpu_rocm_smi() -> List[Dict[str, Any]]:
    if not _which("rocm-smi"):
        return []
    out = _run(["rocm-smi", "-a"], timeout=6)
    arr: List[Dict[str, Any]] = []
    if out:
        d = {"source":"rocm-smi"}
        for line in out.splitlines():
            l = line.strip()
            if "GPU" in l and ":" in l:
                # naive parse
                if "Temperature (Sensor die)" in l or "Temperature" in l:
                    d["temperature_c"] = _to_float(l.split(":")[-1].replace("C","").strip())
                if "Average Graphics Package Power" in l or "Power (Average)" in l:
                    d["power_w"] = _to_float(l.split(":")[-1].replace("W","").strip())
                if "GPU use" in l or "GPU% busy" in l:
                    d["load_percent"] = _to_int(l.split(":")[-1].replace("%","").strip())
        if d:
            arr.append(d)
    return arr

def _gpu_intel_top() -> List[Dict[str, Any]]:
    if not _which("intel_gpu_top"):
        return []
    out = _run(["intel_gpu_top", "-J", "-s", "100", "-o", "-"], timeout=5)
    arr: List[Dict[str, Any]] = []
    try:
        j = json.loads(out)
        # Highly implementation-specific; we'll try to read overall engine busy
        if "engines" in j:
            busy = []
            for e in j["engines"]:
                val = e.get("busy", 0)
                if isinstance(val, (int,float)):
                    busy.append(float(val))
            if busy:
                arr.append({"intel_gpu_busy_avg_percent": round(sum(busy)/len(busy),1), "source":"intel_gpu_top"})
    except Exception:
        pass
    return arr

def get_gpu_info_detailed() -> List[Dict[str, Any]]:
    arr = _gpu_gputil()
    nv = _gpu_nvidia_smi()
    if nv:
        arr.extend(nv)
    amd = _gpu_rocm_smi()
    if amd:
        arr.extend(amd)
    intel = _gpu_intel_top()
    if intel:
        arr.extend(intel)
    # Windows fallback via WMI if still empty
    if _is_windows() and not arr:
        try:
            import wmi  # type: ignore
            c = wmi.WMI()
            for v in c.Win32_VideoController():
                arr.append({
                    "name": getattr(v, "Name", None),
                    "driver": getattr(v, "DriverVersion", None),
                    "memory_total": int(getattr(v, "AdapterRAM", 0) or 0),
                    "pnp_id": getattr(v, "PNPDeviceID", None),
                    "source": "WMI",
                })
        except Exception:
            pass
    return arr

# ---------------- Network ----------------
def _collect_network_addresses() -> List[Dict[str, Any]]:
    arr: List[Dict[str, Any]] = []
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        for name, alist in addrs.items():
            info: Dict[str, Any] = {"name": name}
            st = stats.get(name)
            if st:
                info["is_up"] = st.isup
                info["mtu"] = st.mtu
                info["speed_mbps"] = st.speed if st.speed and st.speed > 0 else None
                if hasattr(st, "duplex"):
                    info["duplex"] = st.duplex
            ipv4_list: List[str] = []
            ipv6_list: List[str] = []
            mac: str | None = None
            for a in alist:
                fam = str(getattr(a.family, "name", a.family))
                if fam.endswith("AF_LINK") or fam.endswith("AF_PACKET"):
                    if a.address and a.address != "00:00:00:00:00:00":
                        mac = a.address
                elif "AF_INET6" in fam:
                    if a.address:
                        ipv6_list.append(a.address.split("%")[0])
                elif "AF_INET" in fam:
                    if a.address:
                        ipv4_list.append(a.address)
            info["mac"] = mac
            if ipv4_list:
                info["ipv4"] = ipv4_list
            if ipv6_list:
                info["ipv6"] = ipv6_list
            arr.append(info)
    except Exception:
        pass
    return arr


def get_network_info_detailed() -> List[Dict[str, Any]]:
    arr = _collect_network_addresses()
    if _is_windows():
        try:
            import wmi  # type: ignore
            c = wmi.WMI()
            by_name: Dict[str, Dict[str, Any]] = {i.get("name", ""): i for i in arr}
            for nic in c.Win32_NetworkAdapterConfiguration(IPEnabled=True):
                name = getattr(nic, "Description", None) or getattr(nic, "Caption", None) or getattr(nic, "ServiceName", None)
                mac = getattr(nic, "MACAddress", None)
                iplist = getattr(nic, "IPAddress", None) or []
                row = None
                if mac:
                    for it in arr:
                        if it.get("mac") and str(it.get("mac")).lower() == str(mac).lower():
                            row = it
                            break
                if row is None and name:
                    for k, it in by_name.items():
                        if k and name and (k in name or name in k):
                            row = it
                            break
                if row is None:
                    row = {"name": name or "WMI_NIC"}
                    arr.append(row)
                if mac and not row.get("mac"):
                    row["mac"] = mac
                if iplist:
                    v4s = [ip for ip in iplist if ip and ":" not in ip]
                    if v4s:
                        existing = set(row.get("ipv4", []))
                        for ip in v4s:
                            existing.add(ip)
                        row["ipv4"] = sorted(list(existing))
        except Exception:
            pass
    return arr


# ---------------- Gather ----------------
def gather_all(spd_json_path: str | None = None, decode_dimms_txt: str | None = None) -> Dict[str, Any]:
    return {
        "collected_at": datetime.now().isoformat(timespec="seconds"),
        "os": get_os_info(),
        "cpu": get_cpu_info_detailed(),
        "memory": get_memory_info_detailed(spd_json_path=spd_json_path, decode_dimms_txt=decode_dimms_txt),
        "motherboard_bios": get_motherboard_bios_section(),
        "gpus": get_gpu_info_detailed(),
        "network": get_network_info_detailed(),
    }
