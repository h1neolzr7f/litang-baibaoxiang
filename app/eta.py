from __future__ import annotations

from typing import Any


class EtaEstimator:
    def __init__(self, seed_sec_per_mb: float = 0.0, seed_sec_per_image: float = 0.0) -> None:
        self.sec_per_mb = float(seed_sec_per_mb or 0.0)
        self.sec_per_image = float(seed_sec_per_image or 0.0)
        self.samples = 0

    def update(self, size_bytes: int, elapsed: float) -> None:
        if elapsed <= 0:
            return
        mb = max(size_bytes, 1) / (1024 * 1024)
        rate_mb = elapsed / mb
        rate_img = elapsed
        if self.samples == 0:
            self.sec_per_mb = rate_mb
            self.sec_per_image = rate_img
        else:
            alpha = 0.28
            self.sec_per_mb = (1 - alpha) * self.sec_per_mb + alpha * rate_mb
            self.sec_per_image = (1 - alpha) * self.sec_per_image + alpha * rate_img
        self.samples += 1

    def remaining(self, leftover_bytes: int, leftover_count: int) -> float | None:
        if leftover_count <= 0:
            return 0.0
        if self.samples <= 0 and self.sec_per_mb <= 0 and self.sec_per_image <= 0:
            return None
        by_size = (leftover_bytes / (1024 * 1024)) * (self.sec_per_mb or 0.0)
        by_count = leftover_count * (self.sec_per_image or 0.0)
        if self.sec_per_mb > 0 and self.sec_per_image > 0:
            return max(0.0, 0.65 * by_size + 0.35 * by_count)
        return max(0.0, by_size or by_count)


def estimate_seconds(total_bytes: int, count: int, cfg: dict[str, Any]) -> float:
    if count <= 0:
        return 0.0
    up = cfg.get("upscale") or {}
    mo = cfg.get("mosaic") or {}
    md = cfg.get("metadata") or {}
    scale = max(1, int(up.get("scale") or 2)) if up.get("enabled", True) else 1
    total_mb = max(total_bytes, 1) / (1024 * 1024)
    perf = cfg.get("perf") or {}
    learned = float(perf.get("sec_per_mb") or 0.0)
    if learned > 0 and int(perf.get("samples") or 0) >= 3:
        return max(8.0, learned * total_mb)

    seconds = count * 0.12
    if md.get("enabled", True):
        seconds += total_mb * 0.04
    if up.get("enabled", True) and scale > 1:
        seconds += total_mb * 0.11 * (scale**2)
    if mo.get("enabled") and cfg.get("mosaic_available"):
        sensitivity = max(1, min(int(mo.get("sensitivity") or 8), 10))
        seconds += count * (1.4 + sensitivity * 0.22)
    return max(8.0, seconds)


def estimate_output_bytes(total_bytes: int, cfg: dict[str, Any]) -> int:
    up = cfg.get("upscale") or {}
    scale = max(1, int(up.get("scale") or 2)) if up.get("enabled", True) else 1
    factor = 0.92
    if up.get("enabled", True) and scale > 1:
        factor = (scale**2) * 0.88
    return max(int(total_bytes * factor), count_floor(total_bytes))


def count_floor(total_bytes: int) -> int:
    return max(int(total_bytes * 0.3), 1)
