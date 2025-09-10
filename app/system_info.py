# app/system_info.py
import os
import sys
import json
import platform
import shutil
import subprocess
from datetime import datetime
from typing import Any, Dict, List

import psutil
from cpuinfo import get_cpu_info

def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def _run(cmd: List[str], timeout: int = 5) -> str:
    """Run a command and return its stdout.

    On Windows, suppresses spawning a console window to avoid flicker when
    polling tools like nvidia-smi from a GUI app.
    """
    try:
        kwargs = dict(text=True, timeout=timeout, stderr=subprocess.STDOUT)
        if _is_windows():
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                kwargs["startupinfo"] = si
                # type: ignore[attr-defined]
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            except Exception:
                pass
        return subprocess.check_output(cmd, **kwargs)
    except Exception:
        return ""

def _is_windows() -> bool:
    return platform.system() == "Windows"

def _read_json_if_exists(p: str):
    try:
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                return json.load(f)
    except Exception:
        pass
    return None

# ---------------- Helpers ----------------
def human_bytes(n: int) -> str:
    units = ["B","KB","MB","GB","TB"]
    i = 0
    f = float(n or 0)
    while f >= 1024 and i < len(units)-1:
        f /= 1024.0
        i += 1
    return f"{f:.2f} {units[i]}"

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
    try:
        import cpuid  # type: ignore
        regs = cpuid.CPUID(0x1).ebx  # bits 15..8 -> CLFLUSH line size * 8
        clflush_line_size = (regs >> 8) & 0xff
        if clflush_line_size:
            return int(clflush_line_size * 8)
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
            if k == "stepping": out["stepping"] = v
            elif k == "model": out["model"] = v
            elif k == "cpu family": out["family"] = v
            elif k == "cache size": out["cache_size"] = v
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
        if not cpus: return {}
        p = cpus[0]
        return {
            "name": getattr(p, "Name", None),
            "manufacturer": getattr(p, "Manufacturer", None),
            "stepping": getattr(p, "Stepping", None),
            "revision": getattr(p, "Revision", None),
            "l2_cache_kb": getattr(p, "L2CacheSize", None),
            "l3_cache_kb": getattr(p, "L3CacheSize", None),
            "max_clock_mhz": getattr(p, "MaxClockSpeed", None),
            "ext_clock_mhz": getattr(p, "ExtClock", None),
        }
    except Exception:
        return {}

def get_cpu_info_detailed() -> Dict[str, Any]:
    base = get_cpu_info() or {}
    freq = psutil.cpu_freq()
    per_core = psutil.cpu_freq(percpu=True) or []
    os_extra: Dict[str, Any] = _cpu_wmi() if _is_windows() else _cpu_linux_proc()
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
        "tdp_watts": None,
    }

# ---------------- Memory ----------------
def _ddr_from_smbios(memtype: int | None) -> str | None:
    try:
        mt = int(memtype) if memtype is not None else None
    except Exception:
        mt = None
    # Common SMBIOS mappings observed in Windows WMI
    mapping = {
        20: "DDR",
        21: "DDR2",
        22: "DDR2 FB-DIMM",
        24: "DDR3",
        26: "DDR4",
        27: "LPDDR",
        28: "LPDDR2",
        29: "LPDDR3",
        30: "LPDDR4",
        31: "Logical non-volatile device",
        32: "HBM",
        33: "HBM2",
        34: "DDR5",
    }
    return mapping.get(mt) if mt is not None else None


def _windows_ram_modules() -> List[Dict[str, Any]]:
    if not _is_windows():
        return []
    try:
        import wmi  # type: ignore
        c = wmi.WMI()
        arr = []
        for m in c.Win32_PhysicalMemory():
            smbios_type = getattr(m, "SMBIOSMemoryType", None)
            ddr = _ddr_from_smbios(smbios_type)
            item = {
                "capacity_bytes": int(getattr(m, "Capacity", 0) or 0),
                "speed_mhz": int(getattr(m, "Speed", 0) or 0) if getattr(m, "Speed", None) else None,
                "configured_speed_mhz": int(getattr(m, "ConfiguredClockSpeed", 0) or 0) if getattr(m, "ConfiguredClockSpeed", None) else None,
                "manufacturer": getattr(m, "Manufacturer", None),
                "part_number": getattr(m, "PartNumber", None),
                "serial": getattr(m, "SerialNumber", None),
                "bank": getattr(m, "BankLabel", None),
                "slot": getattr(m, "DeviceLocator", None),
                "smbios_memory_type": smbios_type,
                "ddr": ddr,
            }
            # Optional useful extras (guarded)
            for opt in ("FormFactor", "TypeDetail", "DataWidth", "TotalWidth"):
                try:
                    val = getattr(m, opt, None)
                    if val not in (None, ""):
                        item[opt[0].lower() + opt[1:]] = val
                except Exception:
                    pass
            arr.append(item)
        return arr
    except Exception:
        return []

def _find_spd_json() -> str | None:
    candidates = [
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "LibreHardwareMonitor", "LibreHardwareMonitorReport.json"),
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "OpenHardwareMonitor", "OpenHardwareMonitorReport.json"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    envp = os.environ.get("MINICPZU_SPD_JSON")
    if envp and os.path.isfile(envp):
        return envp
    return None

def _parse_spd_from_lhm(json_obj: Any) -> List[Dict[str, Any]]:
    out = []
    try:
        text = json.dumps(json_obj)
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
                if "tcl" in lk or "cas latency" in lk: cur["tcl"] = v
                elif "trcd" in lk: cur["trcd"] = v
                elif "trp" in lk: cur["trp"] = v
                elif "tras" in lk: cur["tras"] = v
                elif "trc" in lk: cur["trc"] = v
                elif "voltage" in lk: cur["voltage"] = v
                elif "speed" in lk: cur["speed"] = v
        if cur: out.append(cur)
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

    spd: List[Dict[str, Any]] = []
    path = spd_json_path or _find_spd_json()
    if path:
        j = _read_json_if_exists(path)
        if j: spd = _parse_spd_from_lhm(j)
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
                        from datetime import datetime as _dt
                        dt = _dt.strptime(rd[:14], "%Y%m%d%H%M%S")
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
        if _which("dmidecode"):
            raw = _run(["sudo","dmidecode","-t","baseboard","-t","bios"], timeout=6)
            if raw:
                out["raw_dmidecode"] = raw
    return out

# ---------------- GPU ----------------
def _to_int(x):
    try: return int(float(x))
    except: return None

def _to_float(x):
    try: return float(x)
    except: return None

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
                    "memory_total_mb": _to_int(parts[2]),
                    "memory_used_mb": _to_int(parts[3]),
                    "temperature_c": _to_int(parts[4]),
                    "power_w": _to_float(parts[5]),
                    "fan_percent": _to_int(parts[6].replace("%","")) if "%" in parts[6] else _to_int(parts[6]),
                    "clock_graphics_mhz": _to_int(parts[7]),
                    "clock_mem_mhz": _to_int(parts[8]),
                    "source": "nvidia-smi"
                })
    return arr

def _gpu_rocm_smi() -> List[Dict[str, Any]]:
    if not _which("rocm-smi"):
        return []
    out = _run(["rocm-smi", "-a"], timeout=6)
    arr: List[Dict[str, Any]] = []
    if out:
        d = {"source":"rocm-smi"}
        for line in out.splitlines():
            l = line.strip()
            if "Temperature" in l and ":" in l:
                d["temperature_c"] = _to_float(l.split(":")[-1].replace("C","").strip())
            if "Power" in l and ":" in l:
                d["power_w"] = _to_float(l.split(":")[-1].replace("W","").strip())
            if ("GPU use" in l or "GPU% busy" in l) and ":" in l:
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
    if nv: arr.extend(nv)
    amd = _gpu_rocm_smi()
    if amd: arr.extend(amd)
    intel = _gpu_intel_top()
    if intel: arr.extend(intel)
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

# ---------------- Network ----------------
def get_network_info_detailed() -> List[Dict[str, Any]]:
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    out: List[Dict[str, Any]] = []
    for name, addr_list in addrs.items():
        mac = None
        ipv4 = None
        ipv6 = None
        for a in addr_list:
            # psutil provides family enums; guard access defensively
            fam = getattr(a, 'family', None)
            try:
                from socket import AF_LINK, AF_PACKET, AF_INET, AF_INET6
            except Exception:
                AF_LINK = getattr(psutil, 'AF_LINK', None)
                AF_PACKET = None
                from socket import AF_INET, AF_INET6  # type: ignore

            if fam in (getattr(psutil, 'AF_LINK', None), 'AF_LINK', getattr(psutil, 'AF_LINK', -1), AF_LINK, AF_PACKET):
                if getattr(a, 'address', None):
                    mac = a.address
            elif fam == AF_INET:
                if getattr(a, 'address', None):
                    ipv4 = a.address
            elif fam == AF_INET6:
                addr = getattr(a, 'address', None)
                if addr:
                    # strip scope id if present (e.g., %eth0)
                    ipv6 = addr.split('%')[0]

        st = stats.get(name)
        out.append({
            "name": name,
            "mac": mac,
            "ipv4": ipv4,
            "ipv6": ipv6,
            "is_up": getattr(st, 'isup', None) if st else None,
            "speed_mbps": getattr(st, 'speed', None) if st else None,
            "mtu": getattr(st, 'mtu', None) if st else None,
            "duplex": getattr(st, 'duplex', None) if st else None,
        })
    return out
