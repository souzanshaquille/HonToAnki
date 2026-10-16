#!/usr/bin/env python3
"""
Build script for HonToAnki (Briefcase native apps).

Usage:
    python build_apps.py all          # Build for the current OS (CI covers all OSes)
    python build_apps.py windows      # Windows MSI + ZIP
    python build_apps.py macos        # macOS PKG
    python build_apps.py linux        # Linux deb + rpm
    python build_apps.py portable     # Portable ZIP (Windows only)
"""
import platform as _platform
import subprocess
import sys


def run(cmd, desc):
    print(f"\n=== {desc} ===")
    subprocess.run(cmd, check=True)


def build_platform(platform, package_args, fmt=None):
    cmd = ["briefcase", "create", platform]
    if fmt:
        cmd.append(fmt)
    run(cmd, f"Create {platform} {fmt or ''}")
    cmd = ["briefcase", "build", platform]
    if fmt:
        cmd.append(fmt)
    run(cmd, f"Build {platform} {fmt or ''}")
    for args in package_args:
        cmd = ["briefcase", "package", platform]
        if fmt:
            cmd.append(fmt)
        cmd.extend(args)
        run(cmd, f"Package {platform} {fmt or ''} ({args or 'default'})")


PLATFORM_MAP = {
    "win": "windows",
    "windows": "windows",
    "mac": "macos",
    "macos": "macos",
    "linux": "linux",
}


PLATFORM_BUILD = {
    "windows": ([[], ["-p", "zip"]], None),
    "macos": ([["-p", "pkg", "--adhoc-sign"]], None),
    "linux": ([["-p", "rpm"], ["-p", "deb"]], "system"),
}


def _host_platform():
    system = _platform.system()
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "macos"
    return "linux"


def main():
    args = [a.lower() for a in sys.argv[1:]]
    if not args or "all" in args:
        host = _host_platform()
        print(f"Building for current OS ({host}). All platforms are built in CI via per-OS runners.")
        pkg_args, fmt = PLATFORM_BUILD[host]
        build_platform(host, pkg_args, fmt)
        return

    if "portable" in args:
        if _host_platform() != "windows":
            print("No portable artifact outside Windows (macOS ships PKG, Linux ships deb/rpm).")
            print("Use 'macos' or 'linux' to build the installer for this OS.")
            sys.exit(1)
        build_platform("windows", [["-p", "zip"]])
        return

    for a in args:
        plat = PLATFORM_MAP.get(a)
        if plat in PLATFORM_BUILD:
            pkg_args, fmt = PLATFORM_BUILD[plat]
            build_platform(plat, pkg_args, fmt)

    if not any(a in PLATFORM_MAP for a in args):
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
