import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

if __name__ == "__main__":
    packages = subprocess.check_output([str(PYTHON), "-m", "pip", "freeze"], text=True, encoding="utf-8")
    path = ROOT / "backend" / "requirements.lock.txt"
    path.write_text(packages, encoding="utf-8")
    print(f"Saved {len(packages.splitlines())} installed dependency versions to {path}")
