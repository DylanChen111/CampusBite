"""Record actual command output and exit status as internal development evidence."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=str(ROOT))
    parser.add_argument("--evidence-dir", default="docs/evidence/round03")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    # Files avoid waiting for EOF when a background child inherits a capture pipe.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        result = subprocess.run(command, cwd=args.cwd, stdout=output, stderr=errors,
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        output.seek(0); errors.seek(0)
        stdout = output.read().decode("utf-8", errors="replace")
        stderr = errors.read().decode("utf-8", errors="replace")
    record = dict(started_at=started, finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                  cwd=args.cwd, command=command, exit_code=result.returncode, stdout=stdout, stderr=stderr)
    evidence = ROOT / args.evidence_dir
    evidence.mkdir(parents=True, exist_ok=True)
    with (evidence / "execution.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(stdout + stderr)
    print(f"EXIT_CODE={result.returncode}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
