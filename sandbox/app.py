import base64
import os
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="python-sandbox")

MAX_OUTPUT = 20000
MEMORY_LIMIT = int(os.environ.get("SANDBOX_MEMORY_MB", "512")) * 1024 * 1024
PRELUDE = "import matplotlib\nmatplotlib.use('Agg')\n"


class RunRequest(BaseModel):
    code: str = Field(max_length=50000)
    files: dict[str, str] = Field(default_factory=dict)
    timeout: int = Field(default=20, ge=1, le=60)


def _limits(timeout: int):
    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout + 1))
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
        resource.setrlimit(resource.RLIMIT_FSIZE, (20 * 1024 * 1024, 20 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        os.setsid()

    return apply


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/run")
def run(req: RunRequest) -> dict:
    with tempfile.TemporaryDirectory(prefix="run-") as workdir:
        work = Path(workdir)
        for name, content in req.files.items():
            safe = Path(name).name
            (work / safe).write_text(content, encoding="utf-8")
        script = work / "main.py"
        script.write_text(PRELUDE + req.code, encoding="utf-8")
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": workdir, "MPLCONFIGDIR": workdir, "PYTHONIOENCODING": "utf-8"}
        started = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(script)],
                cwd=workdir,
                env=env,
                capture_output=True,
                timeout=req.timeout,
                preexec_fn=_limits(req.timeout),
            )
            ok = proc.returncode == 0
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired as exc:
            ok = False
            stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
            stderr = f"Превышено время выполнения: {req.timeout} с"
        images = [base64.b64encode(p.read_bytes()).decode() for p in sorted(work.glob("*.png"))[:6]]
        return {
            "ok": ok,
            "stdout": stdout[:MAX_OUTPUT],
            "stderr": stderr[-MAX_OUTPUT:],
            "images": images,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
