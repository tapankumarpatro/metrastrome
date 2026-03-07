"""
GPU detection utility for Metrastrome.

Checks for NVIDIA GPU and VRAM to determine if video call (MuseTalk) is viable.
Requires ~16 GB+ VRAM for real-time lip-sync (RTX 4090/5090 class).

Usage:
    python check_gpu.py          # Print GPU info and recommendation
    python check_gpu.py --json   # Output as JSON (for programmatic use)

Can also be imported:
    from check_gpu import get_gpu_info, is_video_capable
"""

import json
import subprocess
import sys
from typing import Optional


# Minimum VRAM (in MB) required for real-time MuseTalk video generation.
# RTX 4090 = 24 GB, RTX 5090 = 32 GB — both viable.
# RTX 3060 = 12 GB — too slow (~15x slower than real-time).
MIN_VRAM_MB = 16000  # 16 GB


def get_gpu_info() -> list[dict]:
    """Detect NVIDIA GPUs using nvidia-smi. Returns list of GPU info dicts."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.free,driver_version,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []

        gpus = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 6:
                gpus.append({
                    "index": int(parts[0]),
                    "name": parts[1],
                    "vram_total_mb": int(float(parts[2])),
                    "vram_free_mb": int(float(parts[3])),
                    "driver_version": parts[4],
                    "compute_capability": parts[5],
                })
        return gpus
    except FileNotFoundError:
        # nvidia-smi not found — no NVIDIA GPU or drivers not installed
        return []
    except Exception:
        return []


def get_best_gpu() -> Optional[dict]:
    """Return the GPU with the most VRAM, or None if no NVIDIA GPU found."""
    gpus = get_gpu_info()
    if not gpus:
        return None
    return max(gpus, key=lambda g: g["vram_total_mb"])


def is_video_capable() -> bool:
    """Check if the system has a GPU with enough VRAM for video call (MuseTalk)."""
    gpu = get_best_gpu()
    if not gpu:
        return False
    return gpu["vram_total_mb"] >= MIN_VRAM_MB


def get_capability_summary() -> dict:
    """Return a summary of GPU capabilities for the system."""
    gpus = get_gpu_info()
    best = get_best_gpu()
    capable = is_video_capable()

    return {
        "gpu_count": len(gpus),
        "gpus": gpus,
        "best_gpu": best,
        "video_capable": capable,
        "min_vram_required_mb": MIN_VRAM_MB,
        "recommendation": (
            f"Video call supported — {best['name']} with {best['vram_total_mb']} MB VRAM"
            if capable and best
            else (
                f"Video call NOT recommended — {best['name']} has only {best['vram_total_mb']} MB VRAM (need {MIN_VRAM_MB}+ MB)"
                if best
                else "No NVIDIA GPU detected — video call disabled, using audio + text only"
            )
        ),
    }


if __name__ == "__main__":
    summary = get_capability_summary()

    if "--json" in sys.argv:
        print(json.dumps(summary, indent=2))
    else:
        print("=" * 60)
        print("  Metrastrome GPU Check")
        print("=" * 60)

        if summary["gpu_count"] == 0:
            print("\n  No NVIDIA GPU detected.")
            print("  Video call (MuseTalk) will be DISABLED.")
            print("  Audio + text chat will work normally.\n")
        else:
            for gpu in summary["gpus"]:
                print(f"\n  GPU {gpu['index']}: {gpu['name']}")
                print(f"    VRAM: {gpu['vram_total_mb']} MB total, {gpu['vram_free_mb']} MB free")
                print(f"    Driver: {gpu['driver_version']}")
                print(f"    Compute: {gpu['compute_capability']}")

            print(f"\n  Minimum VRAM for video call: {MIN_VRAM_MB} MB")
            print(f"  Video capable: {'YES' : <4} " if summary["video_capable"] else f"  Video capable: {'NO' : <4}")
            print(f"\n  >> {summary['recommendation']}")

        print("\n" + "=" * 60)

        # Print recommended .env setting
        val = "true" if summary["video_capable"] else "false"
        print(f"\n  Recommended .env setting:")
        print(f"    USE_VIDEO_CALL={val}")
        print()
