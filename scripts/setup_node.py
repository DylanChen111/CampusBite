"""Install a portable Node 24 runtime in this workspace on Windows."""

import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".tools"


def main():
    TARGET.mkdir(exist_ok=True)
    with urllib.request.urlopen("https://nodejs.org/dist/index.json", timeout=60) as response:
        release = next(item for item in json.load(response) if item["version"].startswith("v24.") and item["lts"])
    version = release["version"]
    name = f"node-{version}-win-x64.zip"
    archive = TARGET / name
    base = f"https://nodejs.org/dist/{version}/"
    with urllib.request.urlopen(base + "SHASUMS256.txt", timeout=60) as response:
        hashes = dict(line.split()[::-1] for line in response.read().decode().splitlines())
    urllib.request.urlretrieve(base + name, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != hashes[name]:
        raise RuntimeError("Node archive checksum mismatch")
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            if not (TARGET / member.filename).resolve().is_relative_to(TARGET.resolve()):
                raise RuntimeError("Invalid archive path")
        package.extractall(TARGET)
    print(f"Node {version}: {TARGET / name.removesuffix('.zip')}")


if __name__ == "__main__":
    main()
