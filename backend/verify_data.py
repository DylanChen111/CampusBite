"""Run real commands and save tool evidence, never a fabricated chat export."""

import argparse
import difflib
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "round02"


def write_design_evidence(before_dir, evidence_dir):
    evidence_dir.mkdir(parents=True, exist_ok=True)
    diffs = []
    hashes = {}
    for before_path in sorted(before_dir.glob("*.md")):
        after_path = ROOT / "docs" / before_path.name
        before = before_path.read_text(encoding="utf-8")
        after = after_path.read_text(encoding="utf-8")
        diffs.extend(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                     fromfile=f"before/{before_path.name}", tofile=f"after/{before_path.name}"))
        hashes[before_path.name] = {"before_sha256": hashlib.sha256(before_path.read_bytes()).hexdigest(),
                                   "after_sha256": hashlib.sha256(after_path.read_bytes()).hexdigest()}
    (evidence_dir / "design_changes.diff").write_text("".join(diffs), encoding="utf-8")
    (evidence_dir / "design_hashes.json").write_text(json.dumps(hashes, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="执行第二轮验证并保留真实命令证据")
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE)
    parser.add_argument("--history-dir", type=Path, default=ROOT / "docs" / "history" / "round02")
    args = parser.parse_args()
    evidence_dir = (ROOT / args.evidence_dir).resolve()
    before_dir = (ROOT / args.history_dir).resolve()
    write_design_evidence(before_dir, evidence_dir)
    commands = [[sys.executable, "-m", "backend.data", command] for command in ("init", "init", "check", "query")]
    commands.append([sys.executable, "-m", "unittest", "discover", "-s", "backend/tests", "-v"])
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    records = []
    for command in commands:
        started = datetime.now().astimezone().isoformat(timespec="seconds")
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env)
        records.append({"started_at": started, "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "command": command, "cwd": str(ROOT), "exit_code": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr})
        print(f"$ {' '.join(command)}\n{result.stdout}{result.stderr}EXIT_CODE={result.returncode}")
        with (evidence_dir / "execution.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(records[-1], ensure_ascii=False) + "\n")
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
