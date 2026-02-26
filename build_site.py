#!/usr/bin/env python3
"""Static site generator for hub.bulker.io.

Walks all namespace directories, parses YAML manifest files, and generates:
- docs/index.html          -- browsable homepage with search
- docs/<ns>/index.html     -- per-namespace listing
- docs/<ns>/<crate>.html   -- per-crate detail page (one per crate name, all tags)
- docs/channels.html       -- registered channels page
- docs/index.yaml          -- machine-readable manifest index
- docs/index.json          -- same data as JSON (for client-side search)
- docs/style.css           -- stylesheet (copied from _templates/)

Requires: PyYAML, Jinja2 (stdlib otherwise).
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

# Directories to skip when scanning for manifests
SKIP_DIRS = {"docs", "_templates", ".git", ".github", "__pycache__"}

ROOT = Path(__file__).parent.resolve()
DOCS = ROOT / "docs"
TEMPLATES = ROOT / "_templates"


def parse_manifest_file(filepath: Path) -> dict | None:
    """Parse a single manifest YAML file and extract metadata."""
    try:
        with open(filepath) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"  WARNING: could not parse {filepath}: {e}", file=sys.stderr)
        return None

    if not data or "manifest" not in data:
        print(f"  WARNING: no 'manifest' key in {filepath}", file=sys.stderr)
        return None

    manifest = data["manifest"]
    name = manifest.get("name", filepath.stem)
    version = manifest.get("version", "")
    description = manifest.get("description", "")

    # Determine namespace from parent directory name
    namespace = filepath.parent.name

    # Determine tag from filename convention: name_tag.yaml or name.yaml = default
    stem = filepath.stem
    if "_" in stem:
        # e.g. pepatac_1.0.13 -> tag = 1.0.13
        parts = stem.split("_", 1)
        tag = parts[1]
    else:
        tag = "default"

    # Extract commands
    commands_raw = manifest.get("commands") or []
    commands = []
    for cmd in commands_raw:
        if isinstance(cmd, dict):
            commands.append({
                "command": cmd.get("command", ""),
                "docker_image": cmd.get("docker_image", ""),
                "docker_args": cmd.get("docker_args", ""),
                "docker_command": cmd.get("docker_command", ""),
            })

    # Extract other fields
    imports = manifest.get("imports") or []
    host_commands = manifest.get("host_commands") or []

    return {
        "namespace": namespace,
        "name": name,
        "tag": tag,
        "version": str(version) if version else "",
        "description": description or "",
        "path": f"{namespace}/{filepath.name}",
        "filename": filepath.name,
        "commands": commands,
        "command_names": [c["command"] for c in commands],
        "command_count": len(commands),
        "imports": imports,
        "host_commands": host_commands,
        "host_command_count": len(host_commands),
        "raw_yaml": filepath.read_text(),
    }


def discover_manifests(root: Path) -> list[dict]:
    """Walk the repo and find all manifest YAML files."""
    manifests = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue
        namespace_dir = entry
        for yaml_file in sorted(namespace_dir.glob("*.yaml")):
            if yaml_file.is_symlink():
                continue  # skip symlinks, they duplicate a versioned file
            parsed = parse_manifest_file(yaml_file)
            if parsed:
                manifests.append(parsed)
    return manifests


def build_data_structure(manifests: list[dict]) -> dict:
    """Organize manifests into namespaces -> crates -> tags hierarchy."""
    namespaces = {}
    for m in manifests:
        ns = m["namespace"]
        crate_name = m["name"]
        tag = m["tag"]

        if ns not in namespaces:
            namespaces[ns] = {"name": ns, "crates": {}}

        ns_data = namespaces[ns]
        if crate_name not in ns_data["crates"]:
            ns_data["crates"][crate_name] = {
                "name": crate_name,
                "namespace": ns,
                "tags": {},
                "latest_tag": tag,
                "description": m["description"],
            }

        crate_data = ns_data["crates"][crate_name]
        crate_data["tags"][tag] = m

        # Update latest_tag: prefer highest version-like tag, else most recent
        if m["version"]:
            current_latest = crate_data["tags"].get(crate_data["latest_tag"], {})
            current_version = current_latest.get("version", "")
            if _version_gt(m["version"], current_version):
                crate_data["latest_tag"] = tag
                if m["description"]:
                    crate_data["description"] = m["description"]

    return namespaces


def _version_gt(a: str, b: str) -> bool:
    """Compare two version strings. Returns True if a > b."""
    def to_parts(v):
        return [int(x) if x.isdigit() else x for x in re.split(r'[._-]', v)]
    try:
        return to_parts(a) > to_parts(b)
    except (TypeError, ValueError):
        return a > b


def write_index_yaml(manifests: list[dict], output: Path):
    """Write the machine-readable index.yaml."""
    entries = []
    for m in manifests:
        entries.append({
            "namespace": m["namespace"],
            "name": m["name"],
            "tag": m["tag"],
            "path": m["path"],
            "commands": m["command_names"],
            "command_count": m["command_count"],
            "imports": m["imports"],
        })
    with open(output, "w") as f:
        yaml.dump({"manifests": entries}, f, default_flow_style=False, sort_keys=False)
    print(f"  Wrote {output}")


def write_index_json(manifests: list[dict], output: Path):
    """Write index.json for client-side search."""
    entries = []
    for m in manifests:
        entries.append({
            "namespace": m["namespace"],
            "name": m["name"],
            "tag": m["tag"],
            "path": m["path"],
            "commands": m["command_names"],
            "command_count": m["command_count"],
            "imports": m["imports"],
            "description": m["description"],
            "host_commands": m["host_commands"],
        })
    with open(output, "w") as f:
        json.dump({"manifests": entries}, f, indent=2)
    print(f"  Wrote {output}")


def load_channels(root: Path) -> list[dict]:
    """Load channels.yaml from repo root."""
    channels_file = root / "channels.yaml"
    if not channels_file.exists():
        return []
    with open(channels_file) as f:
        data = yaml.safe_load(f)
    return data.get("channels", []) if data else []


def render_site(namespaces: dict, manifests: list[dict], channels: list[dict]):
    """Render all HTML pages using Jinja2 templates."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=True,
    )

    # Compute stats
    total_crates = sum(len(ns["crates"]) for ns in namespaces.values())
    total_commands = sum(m["command_count"] for m in manifests)
    total_namespaces = len(namespaces)
    total_manifests = len(manifests)

    stats = {
        "total_crates": total_crates,
        "total_commands": total_commands,
        "total_namespaces": total_namespaces,
        "total_manifests": total_manifests,
    }

    # Ensure docs/ exists
    DOCS.mkdir(exist_ok=True)

    # Copy style.css and favicon
    css_src = TEMPLATES / "style.css"
    if css_src.exists():
        shutil.copy2(css_src, DOCS / "style.css")
    favicon_src = TEMPLATES / "favicon.svg"
    if favicon_src.exists():
        shutil.copy2(favicon_src, DOCS / "favicon.svg")

    # Render homepage
    tmpl = env.get_template("home.html")
    html = tmpl.render(namespaces=namespaces, stats=stats)
    (DOCS / "index.html").write_text(html)
    print(f"  Wrote docs/index.html")

    # Render namespace pages
    ns_tmpl = env.get_template("namespace.html")
    for ns_name, ns_data in sorted(namespaces.items()):
        ns_dir = DOCS / ns_name
        ns_dir.mkdir(exist_ok=True)
        html = ns_tmpl.render(namespace=ns_data, stats=stats)
        (ns_dir / "index.html").write_text(html)
        print(f"  Wrote docs/{ns_name}/index.html")

    # Render crate pages
    crate_tmpl = env.get_template("crate.html")
    for ns_name, ns_data in sorted(namespaces.items()):
        ns_dir = DOCS / ns_name
        for crate_name, crate_data in sorted(ns_data["crates"].items()):
            html = crate_tmpl.render(crate=crate_data, stats=stats)
            (ns_dir / f"{crate_name}.html").write_text(html)
            print(f"  Wrote docs/{ns_name}/{crate_name}.html")

    # Render channels page
    channels_tmpl = env.get_template("channels.html")
    html = channels_tmpl.render(channels=channels, stats=stats)
    (DOCS / "channels.html").write_text(html)
    print(f"  Wrote docs/channels.html")

    # Copy YAML manifest files into docs/ so CLI URLs work when serving from docs/
    # Symlinks are resolved (copied as regular files) so docs/ is self-contained
    for entry in sorted(ROOT.iterdir()):
        if not entry.is_dir() or entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue
        dest_dir = DOCS / entry.name
        dest_dir.mkdir(exist_ok=True)
        for yaml_file in sorted(entry.glob("*.yaml")):
            # follow_symlinks=True (default) resolves symlinks to regular files
            shutil.copy2(yaml_file, dest_dir / yaml_file.name)
    print(f"  Copied manifest YAML files to docs/")

    # Copy channels.yaml to docs/
    channels_src = ROOT / "channels.yaml"
    if channels_src.exists():
        shutil.copy2(channels_src, DOCS / "channels.yaml")

    # Copy CNAME into docs/
    cname_src = ROOT / "CNAME"
    if cname_src.exists():
        shutil.copy2(cname_src, DOCS / "CNAME")
        print(f"  Copied CNAME to docs/")


def main():
    print("Building hub.bulker.io static site...")
    print()

    print("Discovering manifests...")
    manifests = discover_manifests(ROOT)
    print(f"  Found {len(manifests)} manifests")
    print()

    print("Building data structure...")
    namespaces = build_data_structure(manifests)
    print(f"  {len(namespaces)} namespaces")
    print()

    print("Writing index files...")
    DOCS.mkdir(exist_ok=True)
    write_index_yaml(manifests, DOCS / "index.yaml")
    write_index_json(manifests, DOCS / "index.json")
    print()

    print("Loading channels...")
    channels = load_channels(ROOT)
    print(f"  {len(channels)} channels")
    print()

    print("Rendering HTML pages...")
    render_site(namespaces, manifests, channels)
    print()

    print("Done.")


if __name__ == "__main__":
    main()
