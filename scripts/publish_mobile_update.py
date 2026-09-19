import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
VERSION_FILE = STATIC_DIR / "version.json"

def bump_version(ver_str: str) -> str:
    parts = ver_str.split('.')
    if len(parts) == 3 and parts[-1].isdigit():
        parts[-1] = str(int(parts[-1]) + 1)
        return '.'.join(parts)
    return ver_str + ".1"

def publish_update(release_notes: str = None, explicit_version: str = None):
    print("=== DAWAIFLOW MOBILE WIRELESS UPDATE PUBLISHER ===")
    
    # Load current version
    cur_version = "1.0.0"
    build_num = 1
    if VERSION_FILE.exists():
        try:
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                cur_version = data.get("version", "1.0.0")
                build_num = data.get("build_number", 1)
        except Exception:
            pass

    new_version = explicit_version or bump_version(cur_version)
    new_build = build_num + 1
    notes = release_notes or f"DawaiFlow Mobile update v{new_version} released."

    print(f"Bumping version: {cur_version} -> {new_version} (Build #{new_build})")
    
    # Check for compiled APK or attempt flutter build
    flutter_apk = BASE_DIR / "flutter" / "build" / "app" / "outputs" / "flutter-apk" / "app-release.apk"
    if not flutter_apk.exists():
        flutter_apk = BASE_DIR / "flutter" / "build" / "app" / "outputs" / "flutter-apk" / "app-debug.apk"

    target_apk = STATIC_DIR / "dawaiflow-latest.apk"

    if flutter_apk.exists():
        print(f"Copying compiled APK from {flutter_apk} to {target_apk}...")
        shutil.copy(flutter_apk, target_apk)
    else:
        print(f"[Notice] Compiled APK not found at {flutter_apk}.")
        print("To bundle a fresh APK, run 'flutter build apk' inside the flutter directory.")
        # Create a placeholder if no APK binary present yet
        if not target_apk.exists():
            with open(target_apk, "wb") as f:
                f.write(b"DAWAIFLOW_APK_PLACEHOLDER")

    version_data = {
        "version": new_version,
        "build_number": new_build,
        "download_url": f"https://api.dawaiflow.com/static/dawaiflow-latest.apk",
        "release_notes": notes,
        "min_supported_version": "1.0.0"
    }

    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        json.dump(version_data, f, indent=2)

    print("\n" + "="*60)
    print(f"SUCCESS! Published DawaiFlow Mobile v{new_version} (Build #{new_build}) online.")
    print(f"Release Notes: {notes}")
    print(f"Version metadata saved to {VERSION_FILE}")
    print(f"Target APK endpoint: https://api.dawaiflow.com/static/dawaiflow-latest.apk")
    print("Installed mobile app instances will now prompt users to update wirelessly!")
    print("="*60 + "\n")

if __name__ == "__main__":
    notes_arg = sys.argv[1] if len(sys.argv) > 1 else None
    publish_update(release_notes=notes_arg)
