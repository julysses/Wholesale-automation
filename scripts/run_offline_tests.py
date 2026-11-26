"""Run a local command without inherited secrets, dotenv or provider networking.

Examples:
  .venv/bin/python scripts/run_offline_tests.py .venv/bin/python -m pytest tests
  .venv/bin/python scripts/run_offline_tests.py npm --prefix frontend test

SQL tests should use in-memory PGlite. This runner intentionally blocks even
localhost TCP; real PostgreSQL rehearsals require a separate loopback-only runner.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
guard = root / "scripts" / "offline-tests"
if len(sys.argv) < 2:
    raise SystemExit("Supply a local test command")
with tempfile.TemporaryDirectory(prefix="wholesale-offline-home-") as home:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": home,
        "TMPDIR": tempfile.gettempdir(),
        "LANG": "en_US.UTF-8",
        "CI": "true",
        "PYTHON_DOTENV_DISABLED": "1",
        "PYTHONPATH": os.pathsep.join([str(guard), str(root)]),
        "NODE_OPTIONS": f'--require "{guard / "network.cjs"}"',
        "DATABASE_URL": "sqlite:///:memory:",
    }
    command = sys.argv[1:]
    if command in (["--postgres-sms"], ["--lead-journeys"]):
        # The existing runner creates its own cluster, URL and database, then
        # destroys it in finally. Node may connect only to that generated URL.
        env["PYTHONPATH"] = str(root)
        env["WHOLESALE_LOCAL_POSTGRES"] = "1"
        runner = "run_lead_journeys.py" if command == ["--lead-journeys"] else "run_sms_transport.py"
        command = [sys.executable, str(root / "pipeline/integration" / runner)]
    raise SystemExit(subprocess.run(command, cwd=root, env=env).returncode)
