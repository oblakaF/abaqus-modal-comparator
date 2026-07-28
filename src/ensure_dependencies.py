from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = PROJECT_ROOT / "requirements.txt"
MARKER_PATH = Path(sys.prefix) / ".modal_comparator_requirements.sha256"


def requirements_fingerprint(path: Path = REQUIREMENTS_PATH) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    digest.update(f"|python={sys.version_info.major}.{sys.version_info.minor}".encode("utf-8"))
    return digest.hexdigest()


def dependencies_are_current(
    requirements_path: Path = REQUIREMENTS_PATH,
    marker_path: Path = MARKER_PATH,
) -> bool:
    try:
        return marker_path.read_text(encoding="utf-8").strip() == requirements_fingerprint(
            requirements_path
        )
    except OSError:
        return False


def install_dependencies(
    requirements_path: Path = REQUIREMENTS_PATH,
    marker_path: Path = MARKER_PATH,
) -> None:
    fingerprint = requirements_fingerprint(requirements_path)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            str(requirements_path),
        ],
        cwd=str(PROJECT_ROOT),
        check=True,
    )
    marker_path.write_text(fingerprint, encoding="utf-8")


def main() -> int:
    if dependencies_are_current():
        print("Program dependencies already verified.")
        return 0

    print("Checking program dependencies...")
    install_dependencies()
    print("Program dependencies are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
