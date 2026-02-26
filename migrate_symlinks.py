#!/usr/bin/env python3
"""Migrate bare-name manifest files to symlinks pointing at latest versioned file.

Rules:
1. Bare-name file + versioned copies exist: replace bare with symlink to latest version
2. Bare-name file has version field but no versioned copy: create versioned copy, replace bare with symlink
3. Bare-name file has no version field and no versioned copies: leave alone (unversioned crate)

Run from repo root: python migrate_symlinks.py [--dry-run]
"""

import re
import shutil
import sys
from pathlib import Path

import yaml

SKIP_DIRS = {"docs", "_templates", ".git", ".github", "__pycache__"}
ROOT = Path(__file__).parent.resolve()


VERSION_RE = re.compile(r'^\d+(\.\d+)*$')


def is_version_like(s: str) -> bool:
    """Check if a string looks like a version number (e.g., 1.0.0, 3.21)."""
    return bool(VERSION_RE.match(s))


def version_key(v: str):
    """Parse version string into comparable tuple of ints."""
    return tuple(int(x) for x in v.split("."))


def get_version_from_file(filepath: Path) -> str:
    """Extract manifest.version from a YAML file."""
    try:
        with open(filepath) as f:
            data = yaml.safe_load(f)
        return str(data.get("manifest", {}).get("version", ""))
    except Exception:
        return ""


def migrate_namespace(namespace_dir: Path, dry_run: bool = False):
    """Process all manifests in a namespace directory."""
    # Collect all yaml files, grouping by crate name
    crates = {}  # crate_name -> {"bare": Path|None, "versioned": {version: Path}}
    for yaml_file in sorted(namespace_dir.glob("*.yaml")):
        if yaml_file.is_symlink():
            print(f"  SKIP (already symlink): {yaml_file.name}")
            continue
        stem = yaml_file.stem
        if "_" in stem:
            parts = stem.split("_", 1)
            candidate_name = parts[0]
            candidate_ver = parts[1]
            if is_version_like(candidate_ver):
                crates.setdefault(candidate_name, {"bare": None, "versioned": {}})
                crates[candidate_name]["versioned"][candidate_ver] = yaml_file
            else:
                # Not a version suffix (e.g., demo_strict) — treat as bare-name crate
                crates.setdefault(stem, {"bare": None, "versioned": {}})
                crates[stem]["bare"] = yaml_file
        else:
            crate_name = stem
            crates.setdefault(crate_name, {"bare": None, "versioned": {}})
            crates[crate_name]["bare"] = yaml_file

    for crate_name, info in sorted(crates.items()):
        bare = info["bare"]
        versioned = info["versioned"]

        if not bare and not versioned:
            continue

        # Case: no bare file, only versioned (e.g., refgenie)
        if not bare and versioned:
            latest_ver = max(versioned.keys(), key=version_key)
            target = versioned[latest_ver]
            symlink_path = namespace_dir / f"{crate_name}.yaml"
            print(f"  CREATE symlink: {symlink_path.name} -> {target.name}")
            if not dry_run:
                symlink_path.symlink_to(target.name)
            continue

        # Case: bare file exists
        if bare and versioned:
            # Bare + versioned copies: check if bare content is already saved as a versioned file
            bare_version = get_version_from_file(bare)
            if bare_version and bare_version not in versioned:
                # Save bare content as versioned file first
                versioned_name = f"{crate_name}_{bare_version}.yaml"
                versioned_path = namespace_dir / versioned_name
                print(f"  COPY: {bare.name} -> {versioned_name}")
                if not dry_run:
                    shutil.copy2(bare, versioned_path)
                versioned[bare_version] = versioned_path

            # Now replace bare with symlink to latest
            latest_ver = max(versioned.keys(), key=version_key)
            target = versioned[latest_ver]
            print(f"  SYMLINK: {bare.name} -> {target.name}")
            if not dry_run:
                bare.unlink()
                bare.symlink_to(target.name)
            continue

        if bare and not versioned:
            # Bare-only: check if it has a version field
            bare_version = get_version_from_file(bare)
            if not bare_version:
                print(f"  SKIP (unversioned): {bare.name}")
                continue

            # Has version but no versioned copy: create one and symlink
            versioned_name = f"{crate_name}_{bare_version}.yaml"
            versioned_path = namespace_dir / versioned_name
            print(f"  COPY: {bare.name} -> {versioned_name}")
            print(f"  SYMLINK: {bare.name} -> {versioned_name}")
            if not dry_run:
                shutil.copy2(bare, versioned_path)
                bare.unlink()
                bare.symlink_to(versioned_name)


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN — no changes will be made\n")

    for entry in sorted(ROOT.iterdir()):
        if not entry.is_dir() or entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue
        print(f"Namespace: {entry.name}/")
        migrate_namespace(entry, dry_run=dry_run)
        print()

    print("Done." if not dry_run else "Dry run complete.")


if __name__ == "__main__":
    main()
