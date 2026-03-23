"""
start.py — Single-file startup script for the Insurance Advisory App.

Run from the backend/ folder (or any location):
    python backend/start.py

What it does:
  1. Starts MongoDB + Mongo Express via Docker Compose (infra/)
  2. Waits until MongoDB is accepting connections
  3. Starts the FastAPI backend via uvicorn (backend/)

Requirements:
  - Docker Desktop must be running
  - Python must be in PATH (or run with the venv python)
  - Backend virtualenv must be installed (backend/myenv/)

Press Ctrl+C to stop everything cleanly.
"""

import os
import sys
import time
import signal
import socket
import subprocess
import platform
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).parent.resolve()   # backend/
ROOT = BACKEND_DIR.parent                        # repo root
INFRA_DIR = ROOT / "infra"

IS_WINDOWS = platform.system() == "Windows"

# Virtualenv python / uvicorn paths
if IS_WINDOWS:
    PYTHON = BACKEND_DIR / "myenv" / "Scripts" / "python.exe"
    UVICORN = BACKEND_DIR / "myenv" / "Scripts" / "uvicorn.exe"
else:
    PYTHON = BACKEND_DIR / "myenv" / "bin" / "python"
    UVICORN = BACKEND_DIR / "myenv" / "bin" / "uvicorn"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MONGO_HOST = "localhost"
MONGO_PORT = 27018          # matches docker-compose.yml
BACKEND_PORT = 8000
UVICORN_RELOAD = True       # set False for production-like mode
MONGO_WAIT_TIMEOUT = 60     # seconds to wait for Mongo to be ready
MONGO_WAIT_INTERVAL = 2     # seconds between checks

# ---------------------------------------------------------------------------
# Colours (works on Windows 10+ with ANSI support)
# ---------------------------------------------------------------------------

def _ansi(code: str) -> str:
    return f"\033[{code}m" if sys.stdout.isatty() else ""

RESET  = _ansi("0")
BOLD   = _ansi("1")
GREEN  = _ansi("32")
YELLOW = _ansi("33")
CYAN   = _ansi("36")
RED    = _ansi("31")


def info(msg: str)    -> None: print(f"{CYAN}[INFO]{RESET}  {msg}")
def ok(msg: str)      -> None: print(f"{GREEN}[OK]{RESET}    {msg}")
def warn(msg: str)    -> None: print(f"{YELLOW}[WARN]{RESET}  {msg}")
def error(msg: str)   -> None: print(f"{RED}[ERROR]{RESET} {msg}")
def header(msg: str)  -> None: print(f"\n{BOLD}{CYAN}{msg}{RESET}\n{'─' * len(msg)}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check_docker() -> bool:
    """Return True if Docker daemon is reachable."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def is_port_open(host: str, port: int) -> bool:
    """Return True if a TCP connection can be made to host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect((host, port))
            return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False


def wait_for_mongo() -> bool:
    """
    Poll MongoDB port until it accepts connections or timeout is reached.
    Returns True if Mongo is ready, False if timed out.
    """
    info(f"Waiting for MongoDB on {MONGO_HOST}:{MONGO_PORT} ...")
    deadline = time.time() + MONGO_WAIT_TIMEOUT
    while time.time() < deadline:
        if is_port_open(MONGO_HOST, MONGO_PORT):
            return True
        time.sleep(MONGO_WAIT_INTERVAL)
    return False


# ---------------------------------------------------------------------------
# Process registry (so we can clean up on exit)
# ---------------------------------------------------------------------------

_processes: list[subprocess.Popen] = []


def _shutdown(signum=None, frame=None) -> None:
    print()
    header("Shutting down ...")

    for proc in reversed(_processes):
        if proc.poll() is None:
            info(f"Stopping PID {proc.pid} ...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    # Stop Docker Compose services
    info("Stopping Docker Compose services ...")
    subprocess.run(
        ["docker", "compose", "down"],
        cwd=INFRA_DIR,
        capture_output=True,
    )

    ok("All services stopped. Goodbye.")
    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    header("Insurance Advisory App — Startup")

    # ------------------------------------------------------------------
    # Pre-flight checks
    # ------------------------------------------------------------------
    info("Checking Docker ...")
    if not check_docker():
        error("Docker is not running or not installed. Please start Docker Desktop and try again.")
        sys.exit(1)
    ok("Docker is running.")

    if not BACKEND_DIR.exists():
        error(f"Backend directory not found: {BACKEND_DIR}")
        sys.exit(1)

    if not (PYTHON.exists() or UVICORN.exists()):
        warn(f"Virtualenv not found at {BACKEND_DIR / 'myenv'}.")
        warn("Falling back to system Python. Run 'pip install -r backend/requirements.txt' if needed.")

    uvicorn_cmd = str(UVICORN) if UVICORN.exists() else "uvicorn"

    # ------------------------------------------------------------------
    # Step 1 — Start Docker Compose (MongoDB + Mongo Express)
    # ------------------------------------------------------------------
    header("Step 1 — Starting MongoDB")

    info("Running: docker compose up -d  (in infra/)")
    compose_result = subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=INFRA_DIR,
    )
    if compose_result.returncode != 0:
        error("docker compose up failed. Check Docker Desktop and try again.")
        sys.exit(1)
    ok("Docker Compose started.")

    # ------------------------------------------------------------------
    # Step 2 — Wait for MongoDB to be ready
    # ------------------------------------------------------------------
    header("Step 2 — Waiting for MongoDB")

    if not wait_for_mongo():
        error(f"MongoDB did not become ready within {MONGO_WAIT_TIMEOUT}s.")
        error("Check 'docker compose logs mongodb' in the infra/ directory.")
        _shutdown()

    ok(f"MongoDB is ready on port {MONGO_PORT}.")
    info(f"Mongo Express UI: http://localhost:8082")

    # ------------------------------------------------------------------
    # Step 3 — Start FastAPI backend
    # ------------------------------------------------------------------
    header("Step 3 — Starting FastAPI Backend")

    reload_flag = ["--reload"] if UVICORN_RELOAD else []

    backend_cmd = [
        uvicorn_cmd,
        "app.main:app",
        "--host", "0.0.0.0",
        "--port", str(BACKEND_PORT),
        *reload_flag,
    ]

    info(f"Running: {' '.join(backend_cmd)}  (in backend/)")

    # Set PYTHONPATH so `app` package is importable
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)

    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=BACKEND_DIR,
        env=env,
    )
    _processes.append(backend_proc)

    # Give uvicorn a moment to bind
    time.sleep(2)
    if backend_proc.poll() is not None:
        error("Backend process exited immediately. Check the logs above.")
        _shutdown()

    ok(f"Backend running on http://localhost:{BACKEND_PORT}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    header("All Services Running")
    print(f"  {GREEN}●{RESET} MongoDB          → mongodb://localhost:{MONGO_PORT}")
    print(f"  {GREEN}●{RESET} Mongo Express    → http://localhost:8082")
    print(f"  {GREEN}●{RESET} Backend API      → http://localhost:{BACKEND_PORT}")
    print(f"  {GREEN}●{RESET} API Docs         → http://localhost:{BACKEND_PORT}/api/docs")
    print()
    print(f"  {YELLOW}Frontend:{RESET} cd frontend && npm run dev  →  http://localhost:3000")
    print()
    print(f"  Press {BOLD}Ctrl+C{RESET} to stop all services.")
    print()

    # ------------------------------------------------------------------
    # Keep alive — wait for backend process to exit
    # ------------------------------------------------------------------
    try:
        backend_proc.wait()
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    main()
