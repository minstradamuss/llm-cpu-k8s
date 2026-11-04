import importlib.metadata
import re
import sys
from pathlib import Path


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


expected = {}
for line in Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
    if line.strip():
        name, version = line.split("==")
        expected[normalize(name)] = version
actual = {normalize(item.metadata["Name"]): item.version for item in importlib.metadata.distributions()}
if actual != expected:
    raise SystemExit("Installed dependencies differ from requirements.txt")
print(f"Verified {len(actual)} pinned packages")
