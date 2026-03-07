"""
MuseTalk Auto-Launcher — automatically starts the MuseTalk lip-sync service
when USE_VIDEO_CALL=true, so users don't need to start it manually.

The MuseTalk service runs in its own conda environment ('musetalk') and
listens on port 8001. This module:
  1. Finds the conda 'musetalk' environment Python
  2. Spawns musetalk/service.py as a subprocess
  3. Polls /health until the service is ready
  4. Provides shutdown() to cleanly kill the process
"""

import os
import sys
import time
import atexit
import signal
import subprocess
import asyncio
from pathlib import Path
from loguru import logger

import aiohttp

MUSETALK_URL = os.getenv("MUSETALK_URL", "http://localhost:8001")
MUSETALK_ROOT = Path(__file__).parent.parent / "musetalk"
SERVICE_SCRIPT = MUSETALK_ROOT / "service.py"

# Where to find the conda musetalk env Python
# Try common locations on Windows
CONDA_ENV_CANDIDATES = [
    Path(os.path.expanduser("~")) / ".conda" / "envs" / "musetalk" / "python.exe",
    Path("C:/Users/pc/.conda/envs/musetalk/python.exe"),
    Path("C:/ProgramData/anaconda3/envs/musetalk/python.exe"),
]

_process: subprocess.Popen | None = None


def _find_musetalk_python() -> Path | None:
    """Find the Python executable in the musetalk conda environment."""
    # First try conda run to locate it
    for candidate in CONDA_ENV_CANDIDATES:
        if candidate.exists():
            logger.info(f"[MuseTalk] Found conda Python: {candidate}")
            return candidate

    # Try to find via conda info
    try:
        result = subprocess.run(
            ["conda", "info", "--envs"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if "musetalk" in line.lower():
                env_path = line.split()[-1].strip()
                python_path = Path(env_path) / "python.exe"
                if python_path.exists():
                    logger.info(f"[MuseTalk] Found conda Python via conda info: {python_path}")
                    return python_path
    except Exception as e:
        logger.debug(f"[MuseTalk] conda info failed: {e}")

    return None


def _is_port_in_use(port: int = 8001) -> bool:
    """Check if the MuseTalk port is already in use."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


async def _wait_for_health(timeout: float = 120.0) -> bool:
    """Poll the MuseTalk /health endpoint until it responds or timeout."""
    start = time.time()
    logger.info(f"[MuseTalk] Waiting for service to become healthy (timeout: {timeout}s)...")

    while time.time() - start < timeout:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{MUSETALK_URL}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        elapsed = time.time() - start
                        logger.info(f"[MuseTalk] Service is healthy ({elapsed:.1f}s)")
                        return True
        except Exception:
            pass
        await asyncio.sleep(2)

    logger.error(f"[MuseTalk] Service did not become healthy within {timeout}s")
    return False


def start_service() -> bool:
    """Start the MuseTalk service as a subprocess.

    Returns True if the service was started (or was already running).
    The caller should await wait_for_health() to confirm it's ready.
    """
    global _process

    if not SERVICE_SCRIPT.exists():
        logger.error(f"[MuseTalk] service.py not found at {SERVICE_SCRIPT}")
        return False

    # Check if already running
    if _is_port_in_use(8001):
        logger.info("[MuseTalk] Port 8001 already in use — service may already be running")
        return True

    # Find the conda environment Python
    python_path = _find_musetalk_python()
    if not python_path:
        logger.error(
            "[MuseTalk] Could not find 'musetalk' conda environment. "
            "Please create it: conda create -n musetalk python=3.10 && "
            "conda activate musetalk && pip install -r musetalk/requirements.txt"
        )
        return False

    logger.info(f"[MuseTalk] Starting service: {python_path} {SERVICE_SCRIPT}")
    logger.info(f"[MuseTalk] Working directory: {MUSETALK_ROOT}")

    try:
        # Start the subprocess with the musetalk conda Python
        _process = subprocess.Popen(
            [str(python_path), str(SERVICE_SCRIPT)],
            cwd=str(MUSETALK_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # Don't inherit parent's env completely — use the conda env's
            env={
                **os.environ,
                "PYTHONPATH": str(MUSETALK_ROOT),
            },
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )

        # Register cleanup
        atexit.register(shutdown)

        logger.info(f"[MuseTalk] Process started (PID: {_process.pid})")

        # Start a background thread to log subprocess output
        import threading
        def _log_output():
            if _process and _process.stdout:
                for line in iter(_process.stdout.readline, b""):
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if text:
                        logger.info(f"[MuseTalk:stdout] {text}")
        t = threading.Thread(target=_log_output, daemon=True)
        t.start()

        return True

    except Exception as e:
        logger.error(f"[MuseTalk] Failed to start service: {e}")
        return False


async def ensure_running() -> bool:
    """Start MuseTalk if not running and wait until healthy.

    Call this from the backend startup event when USE_VIDEO_CALL=true.
    """
    started = start_service()
    if not started:
        return False
    return await _wait_for_health(timeout=120)


def shutdown():
    """Cleanly stop the MuseTalk subprocess."""
    global _process
    if _process is None:
        return

    logger.info(f"[MuseTalk] Shutting down service (PID: {_process.pid})...")
    try:
        if sys.platform == "win32":
            # On Windows, send CTRL_BREAK_EVENT to the process group
            _process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            _process.terminate()
        _process.wait(timeout=10)
        logger.info("[MuseTalk] Service stopped cleanly")
    except subprocess.TimeoutExpired:
        logger.warning("[MuseTalk] Force-killing service...")
        _process.kill()
        _process.wait()
    except Exception as e:
        logger.warning(f"[MuseTalk] Shutdown error: {e}")
        try:
            _process.kill()
        except Exception:
            pass
    finally:
        _process = None


def is_running() -> bool:
    """Check if the MuseTalk subprocess is still alive."""
    if _process is None:
        return _is_port_in_use(8001)
    return _process.poll() is None
