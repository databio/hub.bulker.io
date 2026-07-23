#!/usr/bin/env python3
"""Sync the databio/refgenie crate's image pins from bulker/biobase.

Why
---
databio/refgenie is the only crate the refgenie-registry nightly activates, so
it has to be self-contained. But its tools are the same tools biobase pins, and
until 2026-07 the nightly activated `databio/lab,databio/refgenie:1.0.0` --
first-listed-wins -- so biobase silently shadowed 10 of refgenie's 16 commands
and the refgenie manifest stopped describing what actually built the assets.

This script makes that relationship explicit and mechanical: refgenie's pins are
*derived* from biobase, with a reviewable data file (refgenie_crate_sources.yaml)
covering the cases biobase cannot answer directly.

Resolution precedence per command (see refgenie_crate_sources.yaml):
  1. an `overrides` entry                       -> pinned image + stated reason
  2. biobase defines the exact command          -> biobase's image
  3. biobase defines the declared `sibling_of`  -> that package's image
Anything unresolved is a hard error; the script refuses to emit a partial crate.

Overrides outrank biobase deliberately. An override is the one place a human
records "do not take biobase's version of this, and here is why" -- which is
needed both when biobase has no such tool (epilog) and when it has one that
breaks a recipe (bismark 3.x is a Rust rewrite that dropped bowtie1). When an
override shadows an image biobase could have supplied, the script says so on
every run so the hold never becomes invisible.

Cadence is quarterly and the workflow opens a PR -- it never auto-merges.
Every pin change renames published assets and orphans S3 objects, so a bump has
to be a deliberate, reviewed event.

Usage
-----
    python update_refgenie_crate.py                     # report diff only
    python update_refgenie_crate.py --write             # emit next version
    python update_refgenie_crate.py --write --version 1.1.0
    python update_refgenie_crate.py --verify-siblings   # print apptainer checks
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.resolve()
SOURCES = ROOT / "refgenie_crate_sources.yaml"
CRATE_DIR = ROOT / "databio"
CRATE_STEM = "refgenie"


# ---------------------------------------------------------------- manifest io


def newest_manifest(directory: Path, stem: str) -> Path:
    """Return the highest-semver `<stem>_<version>.yaml` in `directory`."""
    candidates = []
    for path in directory.glob(f"{stem}_*.yaml"):
        if path.is_symlink():
            continue
        version = path.stem[len(stem) + 1 :]
        parsed = parse_version(version)
        if parsed is not None:
            candidates.append((parsed, path))
    if not candidates:
        raise SystemExit(f"no versioned {stem} manifest found in {directory}")
    return max(candidates)[1]


def parse_version(version: str) -> tuple[int, ...] | None:
    if not re.fullmatch(r"\d+(\.\d+)*", version):
        return None
    return tuple(int(part) for part in version.split("."))


def load_manifest(path: Path) -> dict:
    with open(path) as handle:
        return yaml.safe_load(handle)["manifest"]


def commands_by_name(manifest: dict) -> dict[str, dict]:
    return {entry["command"]: entry for entry in manifest.get("commands") or []}


# ---------------------------------------------------------------- resolution


def resolve(sources: dict, biobase: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """Apply the three-step precedence to every command the crate must provide.

    Returns (entries, notes). Raises SystemExit if any command is unresolvable,
    so a broken source map can never emit a silently incomplete crate.
    """
    siblings = sources.get("siblings") or {}
    overrides = sources.get("overrides") or {}
    extra_fields = sources.get("extra_fields") or {}

    # `commands` is the authority on what the crate ships. Siblings marked
    # `optional` are documented mappings only -- they are recorded so a future
    # recipe can adopt them without re-deriving the package relationship, but
    # they are NOT emitted until someone adds them to `commands`. A crate that
    # ships commands no recipe uses is noise the reviewer has to re-litigate
    # every quarter.
    wanted = list(sources["commands"])

    entries: list[dict] = []
    notes: list[str] = []
    unresolved: list[str] = []

    for name in sorted(wanted, key=str.lower):
        sibling = siblings.get(name)
        # A sibling marked `optional` is a documented mapping, not an active
        # source; it never resolves anything.
        if sibling and sibling.get("optional"):
            sibling = None

        if name in overrides:
            # Overrides are checked FIRST, ahead of biobase. An override is an
            # explicit human decision -- including the decision to HOLD a
            # command back from a biobase version that exists but breaks a
            # recipe (bismark 3.x dropped bowtie1). If biobase could outrank an
            # override, the escape hatch would be useless for exactly the case
            # it is needed for. Shadowing is announced so it stays visible.
            image = overrides[name]["docker_image"]
            # Availability check uses the RAW sibling entry, optional or not:
            # "what biobase could have supplied" is exactly what the reader
            # needs to see when a hold is in effect.
            raw = siblings.get(name)
            available = (
                biobase.get(name, {}).get("docker_image")
                or (biobase[raw["sibling_of"]]["docker_image"]
                    if raw and raw["sibling_of"] in biobase else None)
            )
            if available:
                notes.append(
                    f"{name}: OVERRIDE holds back biobase's {available} -> {image}"
                )
            else:
                notes.append(f"{name}: override -> {image}")
        elif name in biobase:
            image = biobase[name]["docker_image"]
            notes.append(f"{name}: exact match in biobase -> {image}")
        elif sibling and sibling["sibling_of"] in biobase:
            package = sibling["sibling_of"]
            image = biobase[package]["docker_image"]
            notes.append(f"{name}: sibling of `{package}` -> {image}")
        else:
            unresolved.append(name)
            continue

        entry = {"command": name, "docker_image": image}
        entry.update(extra_fields.get(name) or {})
        entries.append(entry)

    if unresolved:
        raise SystemExit(
            "ERROR: no source for: "
            + ", ".join(unresolved)
            + "\nAdd a `siblings` or `overrides` entry to refgenie_crate_sources.yaml."
        )
    return entries, notes


def bump_minor(version: str) -> str:
    parts = list(parse_version(version) or (1, 0, 0))
    while len(parts) < 3:
        parts.append(0)
    parts[1] += 1
    parts[2] = 0
    return ".".join(str(p) for p in parts)


# ---------------------------------------------------------------------- diff


def diff(old: dict[str, dict], new_entries: list[dict]) -> list[tuple[str, str, str]]:
    rows = []
    new = {e["command"]: e["docker_image"] for e in new_entries}
    for name in sorted(set(old) | set(new), key=str.lower):
        before = old.get(name, {}).get("docker_image", "(absent)")
        after = new.get(name, "(REMOVED)")
        if before != after:
            rows.append((name, before, after))
    return rows


def image_version(image: str) -> str:
    """Best-effort human version from a container reference."""
    tag = image.rsplit(":", 1)[-1] if ":" in image.rsplit("/", 1)[-1] else "latest"
    return tag.split("--")[0]


# ---------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="write the new manifest")
    ap.add_argument("--version", help="explicit new version (default: minor bump)")
    ap.add_argument(
        "--verify-siblings",
        action="store_true",
        help="print the apptainer commands that prove each sibling mapping",
    )
    args = ap.parse_args()

    sources = yaml.safe_load(SOURCES.read_text())
    source_ns, source_name = sources["source_crate"].split("/")
    biobase_path = newest_manifest(ROOT / source_ns, source_name)
    biobase = commands_by_name(load_manifest(biobase_path))

    current_path = newest_manifest(CRATE_DIR, CRATE_STEM)
    current = load_manifest(current_path)
    current_cmds = commands_by_name(current)

    print(f"source crate : {biobase_path.relative_to(ROOT)}")
    print(f"current crate: {current_path.relative_to(ROOT)}")
    print()

    entries, notes = resolve(sources, biobase)

    if args.verify_siblings:
        print("Sibling verification commands (run on a host with apptainer):")
        for name, spec in (sources.get("siblings") or {}).items():
            package = spec["sibling_of"]
            if package not in biobase:
                print(f"  # {name}: SKIP, biobase has no `{package}`")
                continue
            print(
                f"  apptainer exec docker://{biobase[package]['docker_image']}"
                f" which {name}"
            )
        print()

    print("Resolution:")
    for note in notes:
        print(f"  {note}")
    print()

    rows = diff(current_cmds, entries)
    if not rows:
        print("No changes: databio/refgenie already matches biobase.")
        return 0

    width = max(len(r[0]) for r in rows)
    print("Pin changes:")
    for name, before, after in rows:
        print(f"  {name:<{width}}  {before}")
        print(f"  {'':<{width}}  -> {after}")
    print()
    print("Version changes (these RENAME published assets):")
    for name, before, after in rows:
        if before.startswith("(") or after.startswith("("):
            print(f"  {name:<{width}}  {before} -> {after}")
            continue
        bv, av = image_version(before), image_version(after)
        if bv != av:
            print(f"  {name:<{width}}  {bv} -> {av}")
    print()

    new_version = args.version or bump_minor(str(current["version"]))
    out_path = CRATE_DIR / f"{CRATE_STEM}_{new_version}.yaml"

    manifest = {
        "manifest": {
            "name": current["name"],
            "version": new_version,
            "description": (
                "Containerized tools for building refgenie reference assets. "
                "Self-contained: activate this crate alone. Image pins are "
                "synced quarterly from bulker/biobase by update_refgenie_crate.py."
            ),
            "imports": list(sources.get("imports") or []),
            "commands": entries,
        }
    }

    if not args.write:
        print(f"(dry run) would write {out_path.relative_to(ROOT)}")
        return 0

    with open(out_path, "w") as handle:
        yaml.safe_dump(manifest, handle, sort_keys=False, default_flow_style=False)
    print(f"wrote {out_path.relative_to(ROOT)}")
    print(f"remember: ln -sf {out_path.name} {CRATE_DIR / (CRATE_STEM + '.yaml')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
