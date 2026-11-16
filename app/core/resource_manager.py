from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Callable

import psutil

from .project_paths import CONFIG_DIR, confine_output_path, load_paths


PROFILE_AUTOMATIC = "automatic"
PROFILE_ECONOMIC = "economic"
PROFILE_BALANCED = "balanced"
ALLOWED_PROFILES = {PROFILE_AUTOMATIC, PROFILE_ECONOMIC, PROFILE_BALANCED}


@dataclass(frozen=True)
class ResourceProfile:
    """A concrete, CPU-only execution plan for one generation job."""

    profile_id: str
    label: str
    threads: int
    chunk_chars: int = 280
    throttle_seconds: float = 0.0
    sequential: bool = True
    adaptive: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResourceSnapshot:
    available_ram_gb: float
    disk_free_gb: float
    battery_percent: int | None
    plugged_in: bool | None
    system_cpu_percent: float
    process_ram_mb: float
    total_ram_gb: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResourceDecision:
    allowed: bool
    snapshot: ResourceSnapshot
    warnings: tuple[str, ...] = ()
    blocks: tuple[str, ...] = ()
    plan: dict = field(default_factory=dict)


class ResourcePressureError(RuntimeError):
    """Raised only after the configured recovery window cannot restore RAM."""


def load_resource_policy() -> dict:
    return json.loads((CONFIG_DIR / "resource_policy.json").read_text(encoding="utf-8"))


def _logical_cores() -> int:
    return max(1, psutil.cpu_count(logical=True) or 1)


def _safety_margin_gb(snapshot: ResourceSnapshot, policy: dict) -> float:
    adaptive = policy["adaptive"]
    total_ram = snapshot.total_ram_gb or 0.0
    return round(
        max(
            float(adaptive["minimum_system_reserve_gb"]),
            total_ram * float(adaptive["system_reserve_fraction"]),
        ),
        3,
    )


def _automatic_profile(raw: dict, snapshot: ResourceSnapshot | None, text_characters: int, policy: dict) -> ResourceProfile:
    adaptive = policy["adaptive"]
    logical_cores = _logical_cores()
    available_ram = snapshot.available_ram_gb if snapshot is not None else float("inf")
    cpu_load = snapshot.system_cpu_percent if snapshot is not None else 0.0
    low_ram = float(adaptive["low_ram_gb"])
    medium_ram = float(adaptive["medium_ram_gb"])
    high_cpu = float(adaptive["high_cpu_percent"])
    medium_cpu = float(adaptive["medium_cpu_percent"])

    if available_ram <= low_ram or cpu_load >= high_cpu:
        tier = "conservative"
    elif available_ram <= medium_ram or cpu_load >= medium_cpu:
        tier = "reduced"
    else:
        tier = "normal"
    settings = adaptive["tiers"][tier]
    # Leave scheduling capacity for the desktop on smaller machines.
    threads = max(1, min(int(settings["max_threads"]), logical_cores // 2))
    chunk_chars = int(settings["chunk_chars"])
    # A short request never needs artificial subdivision; long requests receive
    # the conservative chunk size selected from the current machine state.
    if text_characters and text_characters <= chunk_chars:
        chunk_chars = max(chunk_chars, text_characters)
    return ResourceProfile(
        PROFILE_AUTOMATIC,
        str(raw["label"]),
        threads,
        chunk_chars=chunk_chars,
        throttle_seconds=float(settings["throttle_seconds"]),
        sequential=True,
        adaptive=True,
    )


def resolve_profile(
    profile_id: str | None = None,
    policy: dict | None = None,
    *,
    snapshot: ResourceSnapshot | None = None,
    text_characters: int = 0,
) -> ResourceProfile:
    policy = policy or load_resource_policy()
    selected = profile_id or policy["default_profile"]
    if selected not in ALLOWED_PROFILES or selected not in policy["profiles"]:
        raise ValueError("Unknown resource profile")
    raw = policy["profiles"][selected]
    if selected == PROFILE_AUTOMATIC:
        return _automatic_profile(raw, snapshot, text_characters, policy)

    logical_cores = _logical_cores()
    if "threads" in raw:
        threads = max(1, min(int(raw["threads"]), logical_cores))
    else:
        fraction = float(raw.get("cpu_fraction", 0.5))
        maximum = int(raw.get("max_threads", 4))
        threads = max(1, min(maximum, logical_cores, int(logical_cores * fraction)))
    return ResourceProfile(
        selected,
        str(raw["label"]),
        threads,
        chunk_chars=int(raw.get("chunk_chars", 280)),
        throttle_seconds=float(raw.get("throttle_seconds", 0.0)),
        sequential=True,
        adaptive=False,
    )


def apply_runtime_limits(profile: ResourceProfile) -> dict:
    value = str(profile.threads)
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = value
    priority_applied = False
    try:
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        priority_applied = True
    except (AttributeError, OSError, psutil.Error):
        priority_applied = False
    return {
        "profile": profile.profile_id,
        "threads": profile.threads,
        "chunk_chars": profile.chunk_chars,
        "throttle_seconds": profile.throttle_seconds,
        "sequential": profile.sequential,
        "priority_below_normal": priority_applied,
    }


class AdaptiveController:
    """Observe continuously; apply thread changes only between synthesis calls."""

    def __init__(self, profile: ResourceProfile, policy: dict | None = None) -> None:
        self.policy = policy or load_resource_policy()
        self._profile = profile
        self._lock = threading.Lock()
        self._candidate: ResourceProfile | None = None
        self._since = 0.0
        self._samples = 0

    def observe(self, snapshot: ResourceSnapshot) -> ResourceProfile:
        with self._lock:
            if not self._profile.adaptive:
                return self._profile
            proposed = resolve_profile(PROFILE_AUTOMATIC, self.policy, snapshot=snapshot)
            # Preserve the approved text boundaries throughout this job.
            proposed = replace(proposed, chunk_chars=self._profile.chunk_chars)
            slower = (proposed.threads < self._profile.threads or
                      proposed.throttle_seconds > self._profile.throttle_seconds)
            if slower or proposed == self._profile:
                self._profile = proposed
                self._candidate = None
                self._samples = 0
            else:
                now = time.monotonic()
                if proposed != self._candidate:
                    self._candidate, self._since, self._samples = proposed, now, 0
                self._samples += 1
                adaptive = self.policy['adaptive']
                if (self._samples >= int(adaptive.get('speedup_samples', 3)) and
                        now - self._since >= float(adaptive.get('speedup_stable_seconds', 5.0))):
                    self._profile = proposed
                    self._candidate = None
                    self._samples = 0
            return self._profile

    def current(self) -> ResourceProfile:
        with self._lock:
            return self._profile


def capture_snapshot(output_dir: Path | None = None) -> ResourceSnapshot:
    target = confine_output_path(output_dir or load_paths()["generation_output_dir"], label="resource output", allow_root=True)
    target.mkdir(parents=True, exist_ok=True)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(target))
    battery = psutil.sensors_battery()
    process = psutil.Process()
    return ResourceSnapshot(
        available_ram_gb=round(memory.available / (1024**3), 3),
        disk_free_gb=round(disk.free / (1024**3), 3),
        battery_percent=None if battery is None else int(round(battery.percent)),
        plugged_in=None if battery is None else bool(battery.power_plugged),
        system_cpu_percent=round(float(psutil.cpu_percent(interval=None)), 1),
        process_ram_mb=round(process.memory_info().rss / (1024**2), 1),
        total_ram_gb=round(memory.total / (1024**3), 3),
    )


def evaluate_resources(
    profile_id: str | None = None,
    *,
    snapshot: ResourceSnapshot | None = None,
    policy: dict | None = None,
    output_dir: Path | None = None,
    text_characters: int = 0,
) -> ResourceDecision:
    """Evaluate a measured safety margin instead of a fixed free-RAM gate."""

    policy = policy or load_resource_policy()
    current = snapshot or capture_snapshot(output_dir)
    profile = resolve_profile(profile_id, policy, snapshot=current, text_characters=text_characters)
    limits = policy["thresholds"]
    adaptive = policy["adaptive"]
    reserve_gb = _safety_margin_gb(current, policy)
    minimum_start_gb = reserve_gb + float(adaptive["cold_start_headroom_gb"])
    warnings: list[str] = []
    blocks: list[str] = []

    if current.available_ram_gb < minimum_start_gb:
        blocks.append("Memoria livre abaixo da margem segura calculada para o Windows e o modelo.")
    elif current.available_ram_gb < reserve_gb + float(limits["ram_warn_headroom_gb"]):
        warnings.append("Memoria livre limitada: o processamento sera sequencial e com ritmo reduzido quando necessario.")
    if current.disk_free_gb < float(limits["disk_block_gb"]):
        blocks.append("Espaco livre em disco insuficiente para a geracao.")
    elif current.disk_free_gb < float(limits["disk_warn_gb"]):
        warnings.append("Espaco livre em disco proximo do limite recomendado.")
    if current.battery_percent is not None and current.plugged_in is False:
        if current.battery_percent <= int(limits["battery_block_percent"]):
            blocks.append("Bateria muito baixa. Conecte o computador a energia.")
        elif current.battery_percent <= int(limits["battery_warn_percent"]):
            warnings.append("Bateria baixa; prefira conectar o computador a energia.")

    plan = {
        "profile": profile.to_dict(),
        "safe_system_reserve_gb": reserve_gb,
        "minimum_start_available_gb": round(minimum_start_gb, 3),
        "available_after_reserve_gb": round(current.available_ram_gb - reserve_gb, 3),
        "text_characters": int(text_characters),
    }
    return ResourceDecision(not blocks, current, tuple(warnings), tuple(blocks), plan)


def wait_for_memory_recovery(
    output_dir: Path | None,
    *,
    callback: Callable[[dict], None] | None = None,
    cancel_event: threading.Event | None = None,
    policy: dict | None = None,
) -> ResourceSnapshot:
    """Wait briefly for RAM to recover before a safe job cancellation is required."""

    policy = policy or load_resource_policy()
    adaptive = policy["adaptive"]
    interval = float(adaptive["recovery_poll_seconds"])
    deadline = time.monotonic() + float(adaptive["max_recovery_wait_seconds"])
    latest = capture_snapshot(output_dir)
    # Recovery must satisfy the same RAM gate used immediately afterwards.
    def recovery_target(snapshot: ResourceSnapshot) -> float:
        return max(
            float(adaptive["runtime_recovery_ram_gb"]),
            _safety_margin_gb(snapshot, policy) + float(adaptive["cold_start_headroom_gb"]),
        )

    while latest.available_ram_gb < recovery_target(latest):
        if callback:
            callback(latest.to_dict())
        if cancel_event is not None and cancel_event.is_set():
            return latest
        if time.monotonic() >= deadline:
            raise ResourcePressureError("Memoria livre permaneceu abaixo da margem critica; o job foi interrompido com seguranca.")
        time.sleep(interval)
        latest = capture_snapshot(output_dir)
    if callback:
        callback(latest.to_dict())
    return latest


ResourceCallback = Callable[[dict], None]


class ResourceMonitor:
    def __init__(self, output_dir: Path, callback: ResourceCallback | None = None, interval: float | None = None) -> None:
        policy = load_resource_policy()
        self.output_dir = output_dir
        self.callback = callback
        self.interval = float(interval or policy["monitor_interval_seconds"])
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._samples: list[ResourceSnapshot] = []

    def start(self) -> None:
        if self._thread is not None:
            return
        self._record()
        self._thread = threading.Thread(target=self._run, name="v2-resource-monitor", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._record()

    def _record(self) -> None:
        sample = capture_snapshot(self.output_dir)
        self._samples.append(sample)
        if self.callback:
            try:
                self.callback(sample.to_dict())
            except Exception:
                pass

    def stop(self) -> dict:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval * 2))
        if not self._samples:
            self._record()
        return self.summary()

    def summary(self) -> dict:
        samples = self._samples
        return {
            "samples": len(samples),
            "max_system_cpu_percent": max(item.system_cpu_percent for item in samples),
            "max_process_ram_mb": max(item.process_ram_mb for item in samples),
            "min_available_ram_gb": min(item.available_ram_gb for item in samples),
            "min_disk_free_gb": min(item.disk_free_gb for item in samples),
        }
