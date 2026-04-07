"""
install.py
----------
Downloads the correct pre-built py-melonds binary for the current
platform and extracts it into a melonds/ folder next to this script.

Usage from your project:

    from pathlib import Path
    from install import install_melonds
    install_melonds(target_dir=Path("melonds"), version="v0.1.0")

Or run directly:

    python install.py
    python install.py v0.2.0
"""

from __future__ import annotations

import io
import platform
import sys
import zipfile
from pathlib import Path

# Replace with your actual GitHub username/repo after publishing
GITHUB_RELEASES_URL = "https://github.com/bumblebrown/py-melonds/releases/download"

_PLATFORM_MAP = {
    ("Windows", "AMD64"):  "win64",
    ("Windows", "x86_64"): "win64",
    ("Linux",   "x86_64"): "linux-x86_64",
    ("Darwin",  "x86_64"): "macos-x86_64",
    ("Darwin",  "arm64"):  "macos-arm64",
}


def get_platform_suffix() -> str:
    system  = platform.system()
    machine = platform.machine()
    suffix  = _PLATFORM_MAP.get((system, machine))
    if suffix is None:
        raise RuntimeError(
            f"Unsupported platform: {system} {machine}. "
            "Supported: Windows x64, Linux x86_64, macOS Intel, macOS Apple Silicon."
        )
    return suffix


def install_melonds(
    target_dir: Path | str = Path("melonds"),
    version:    str        = "v0.1.0",
    force:      bool       = False,
) -> None:
    """
    Download and extract py-melonds into target_dir.

    Parameters
    ----------
    target_dir  Where to extract the melonds/ package.
    version     Release tag to download, e.g. "v0.1.0".
    force       Re-download even if already installed at this version.
    """
    target_dir   = Path(target_dir)
    version_file = target_dir / ".version"

    if not force and target_dir.is_dir() and version_file.exists():
        if version_file.read_text().strip() == version:
            return

    suffix   = get_platform_suffix()
    zip_name = f"py-melonds-{version}-{suffix}.zip"
    url      = f"{GITHUB_RELEASES_URL}/{version}/{zip_name}"

    print(f"Downloading py-melonds {version} for {platform.system()} ({platform.machine()})...")
    print(f"  {url}")

    try:
        import urllib.request
        with urllib.request.urlopen(url) as response:
            data = response.read()
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download py-melonds from {url}\n"
            f"Error: {exc}\n"
            "Check your internet connection or download the zip manually."
        ) from exc

    if target_dir.exists():
        import shutil
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(target_dir)

    version_file.write_text(version)
    print(f"  Installed to {target_dir.resolve()}")


def is_installed(
    target_dir: Path | str = Path("melonds"),
    version:    str        = "v0.1.0",
) -> bool:
    target_dir   = Path(target_dir)
    version_file = target_dir / ".version"
    if not target_dir.is_dir() or not version_file.exists():
        return False
    return version_file.read_text().strip() == version


if __name__ == "__main__":
    version = sys.argv[1] if len(sys.argv) > 1 else "v0.1.0"
    try:
        install_melonds(version=version)
        print("Done. You can now use: from melonds import MelonDSEmulator")
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
