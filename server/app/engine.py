import json
import subprocess
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[2] / "engine"

TOOLS = {
    "scanner": ("trader-scanner", "scan.py"),
    "news": ("trader-news", "news.py"),
    "entry": ("trader-entry", "entry.py"),
    "exit": ("trader-exit", "exit.py"),
    "timemachine": ("trader-timemachine", "timemachine.py"),
    "budget": ("trader-budget", "size.py"),
    "risk": ("trader-risk", "check.py"),
}


class EngineError(Exception):
    def __init__(self, message: str, returncode: int = 1, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


def run_tool(tool: str, args: list[str], workdir: Path, timeout: int = 300,
             engine_dir: Path = ENGINE_DIR) -> dict:
    """Run a skill tool with --json inside workdir and return its parsed JSON."""
    folder, script = TOOLS[tool]
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(Path(engine_dir) / folder / script), *args, "--json"]
    try:
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise EngineError("A ferramenta %s demorou demais." % tool, 124, "timeout")
    if proc.returncode != 0:
        # Algumas ferramentas usam exit 1 como alerta ("há algo novo") e ainda assim imprimem JSON.
        try:
            doc = json.loads(proc.stdout)
            if isinstance(doc, dict):
                return doc
        except json.JSONDecodeError:
            pass
        msg = (proc.stderr or proc.stdout).strip().splitlines()
        raise EngineError(msg[-1] if msg else "A ferramenta %s falhou." % tool,
                          proc.returncode, proc.stderr)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise EngineError("A ferramenta %s não devolveu JSON." % tool, 0, proc.stdout[:500])
