"""Run the local studio, API and CPU analysis worker together."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local"
RUNNING = STATE / "studio.pid"


def development_env(sqlite):
    env = os.environ.copy()
    if sqlite:
        db_file = (STATE / "sqlite" / "creatoros.db").resolve()
        db_file.parent.mkdir(parents=True, exist_ok=True)
        env["DATABASE_URL"] = "sqlite:///" + db_file.as_posix()
    elif not env.get("DATABASE_URL"):
        settings = STATE / "database.env"
        if settings.exists():
            for line in settings.read_text(encoding="utf-8-sig").splitlines():
                key, _, value = line.partition("=")
                if key == "DATABASE_URL":
                    env[key] = value.strip()
    if not env.get("DATABASE_URL"):
        raise SystemExit("Set DATABASE_URL for PostgreSQL, or use --sqlite for a lightweight local database.")
    env.setdefault("PGCONNECT_TIMEOUT", "8")
    env.setdefault("STORAGE_ROOT", str(STATE / ("sqlite" if sqlite else "postgres") / "sources"))
    if not env.get("FFPROBE_BIN"):
        installed = shutil.which("ffprobe")
        portable = next((STATE / "media").glob("*/bin/ffprobe.exe"), None)
        if installed or portable:
            env["FFPROBE_BIN"] = str(installed or portable)
    if not env.get("FFMPEG_BIN") and env.get("FFPROBE_BIN"):
        probe = Path(env["FFPROBE_BIN"])
        encoder = probe.with_name("ffmpeg" + probe.suffix)
        if encoder.is_file():
            env["FFMPEG_BIN"] = str(encoder)
    env.setdefault("WHISPER_MODEL_PATH", str(STATE / "models" / "faster-whisper-base"))
    return env


def check_port(port):
    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    except OSError:
        raise SystemExit(f"Port {port} is in use. Stop the existing local service before starting another.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", action="store_true", help="Use a persistent local SQLite database.")
    parser.add_argument("--stop", action="store_true", help="Stop this workspace's native studio processes.")
    options = parser.parse_args()
    if options.stop:
        pid = RUNNING.read_text().strip() if RUNNING.is_file() else ""
        if not pid.isdecimal():
            raise SystemExit("No native studio is registered in this workspace.")
        (STATE / f"studio-{pid}.stop").touch()
        print("Requested shutdown of the native studio processes.")
        return
    env = development_env(options.sqlite)
    api = ROOT / "backend"
    frontend = ROOT / "frontend"
    vite = frontend / "node_modules" / "vite" / "bin" / "vite.js"
    node = shutil.which("node")
    if not node or not vite.is_file():
        raise SystemExit("Install Node.js and run npm ci in frontend first.")
    for port in (8000, 5173):
        check_port(port)
    model = Path(env.get("CLIP_MODEL_PATH", str(STATE / "models" / "qwen2.5-1.5b-instruct-q4_k_m.gguf")))
    server = env.get("LLAMA_SERVER_BIN") or shutil.which("llama-server") or str(STATE / "llama" / "llama-server.exe")
    managed_model = not env.get("CLIP_LLM_URL") and Path(server).is_file() and model.is_file()
    if managed_model:
        check_port(8099)
    worker_bin = STATE / "worker-venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    worker_python = env.get("CREATOROS_WORKER_PYTHON") or (str(worker_bin) if worker_bin.is_file() else sys.executable)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=api, env=env, check=True)
    processes = []
    pid = str(os.getpid())
    stop_request = STATE / f"studio-{pid}.stop"
    try:
        if managed_model:
            alias = env.get("CLIP_LLM_MODEL", "qwen2.5-1.5b-instruct-q4_k_m")
            processes.append(subprocess.Popen(
                [server, "-m", str(model), "--alias", alias, "--host", "127.0.0.1", "--port", "8099",
                 "--threads", "4", "--ctx-size", "8192", "--parallel", "1", "--n-gpu-layers", "0",
                 "--offline", "--no-webui"], cwd=api,
            ))
        processes.append(subprocess.Popen([worker_python, "-m", "app.worker"], cwd=api, env=env))
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=api, env=env,
        ))
        env["CREATOROS_API_URL"] = "http://127.0.0.1:8000"
        processes.append(subprocess.Popen([node, str(vite)], cwd=frontend, env=env))
        STATE.mkdir(exist_ok=True)
        RUNNING.write_text(pid, encoding="ascii")
        print("Studio at http://127.0.0.1:5173 | API docs at http://127.0.0.1:5173/api/v1/docs", flush=True)
        while all(process.poll() is None for process in processes):
            if stop_request.exists():
                return
            time.sleep(0.5)
        raise SystemExit(next(process.returncode for process in processes if process.returncode is not None))
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if RUNNING.is_file() and RUNNING.read_text().strip() == pid:
            RUNNING.unlink(missing_ok=True)
        stop_request.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
