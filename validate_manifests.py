#!/usr/bin/env python3
"""Validate bulker manifests for hub.bulker.io.

Modes:
    python validate_manifests.py              # Tier 1: structural only (no network)
    python validate_manifests.py --check-tags # Tier 1 + Tier 2: verify image tags exist
    python validate_manifests.py --sort       # Sort commands alphabetically in-place

Exit code 0 = all valid, exit code 1 = errors found.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.resolve()
SKIP_DIRS = {"docs", "_templates", ".git", ".github", "__pycache__"}

# Pattern for import references: namespace/crate:tag
IMPORT_RE = re.compile(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+:[a-zA-Z0-9_.-]+$")

# Docker image: optional registry, repo (with optional namespace), optional tag
DOCKER_IMAGE_RE = re.compile(r"^[a-zA-Z0-9._/-]+(:[a-zA-Z0-9._-]+)?$")


class ValidationResult:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    def info(self, msg: str):
        self.infos.append(msg)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def discover_manifest_files(root: Path) -> list[Path]:
    """Find all manifest YAML files (excluding docs/, _templates/, etc.)."""
    files = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue
        for yaml_file in sorted(entry.glob("*.yaml")):
            files.append(yaml_file)
    return files


def validate_structure(filepath: Path) -> ValidationResult:
    """Tier 1: Structural validation of a single manifest file."""
    rel = filepath.relative_to(ROOT)
    result = ValidationResult(str(rel))

    # Parse YAML
    try:
        with open(filepath) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        result.error(f"YAML parse error: {e}")
        return result

    if not isinstance(data, dict):
        result.error("File does not contain a YAML mapping")
        return result

    # Top-level 'manifest' key
    if "manifest" not in data:
        result.error("Missing top-level 'manifest' key")
        return result

    manifest = data["manifest"]
    if not isinstance(manifest, dict):
        result.error("'manifest' is not a mapping")
        return result

    # manifest.name — must be namespaced (namespace/crate)
    name = manifest.get("name")
    if not name or not isinstance(name, str) or not name.strip():
        result.error("Missing or empty 'manifest.name'")
    elif "/" not in name:
        result.error(f"manifest.name '{name}' has no namespace (expected 'namespace/crate')")
    else:
        # Parse namespace/crate from name
        name_ns, name_crate = name.split("/", 1)
        # Namespace must match parent directory
        parent_dir = filepath.parent.name
        if name_ns != parent_dir:
            result.error(f"manifest.name namespace '{name_ns}' does not match directory '{parent_dir}'")
        # Crate name must match filename stem (stripping version suffix)
        stem = filepath.stem
        expected = stem.split("_", 1)[0] if "_" in stem else stem
        if name_crate != expected:
            result.warn(f"manifest.name crate '{name_crate}' does not match filename stem '{expected}'")

    # manifest.version (warn if missing -- some host-command-only manifests omit it)
    version = manifest.get("version")
    if version is None or (isinstance(version, str) and not version.strip()):
        result.warn("Missing or empty 'manifest.version'")

    # manifest.commands -- may be null/missing for host-command-only manifests
    commands = manifest.get("commands")
    host_commands = manifest.get("host_commands")
    if (commands is None or commands == []) and host_commands:
        result.info(f"Host-command-only manifest ({len(host_commands)} host commands)")
        return result
    if commands is None or (isinstance(commands, list) and len(commands) == 0):
        result.error("'manifest.commands' is missing or empty (and no host_commands)")
        return result
    if not isinstance(commands, list):
        result.error("'manifest.commands' must be a list")
        return result

    # Validate each command
    command_names = []
    images = []
    for i, cmd in enumerate(commands):
        if not isinstance(cmd, dict):
            result.error(f"Command #{i+1} is not a mapping")
            continue

        cmd_name = cmd.get("command")
        if not cmd_name or not isinstance(cmd_name, str) or not cmd_name.strip():
            result.error(f"Command #{i+1}: missing or empty 'command' field")
        else:
            command_names.append(cmd_name)

        img = cmd.get("docker_image")
        if not img or not isinstance(img, str) or not img.strip():
            result.error(f"Command '{cmd_name or f'#{i+1}'}': missing or empty 'docker_image'")
        else:
            images.append(img.strip())
            # Whitespace check
            if " " in img or "\t" in img:
                result.error(f"Command '{cmd_name}': docker_image contains whitespace: '{img}'")
            # Format check
            elif not DOCKER_IMAGE_RE.match(img.strip()):
                result.error(f"Command '{cmd_name}': invalid docker_image format: '{img}'")
            # Tag check
            elif ":" not in img:
                result.warn(f"Command '{cmd_name}': image '{img}' has no explicit tag (will use :latest)")

        # Optional string fields
        for field in ("docker_command", "docker_args", "description"):
            val = cmd.get(field)
            if val is not None and not isinstance(val, str):
                result.warn(f"Command '{cmd_name}': '{field}' should be a string, got {type(val).__name__}")

    result.info(f"Schema valid ({len(commands)} commands)")

    # Duplicate command names
    seen = {}
    for cn in command_names:
        seen[cn] = seen.get(cn, 0) + 1
    dupes = {k: v for k, v in seen.items() if v > 1}
    if dupes:
        for name_dup, count in dupes.items():
            result.error(f"Duplicate command: \"{name_dup}\" (appears {count} times)")
    else:
        result.info("No duplicate commands")

    # Import reference validation
    imports = manifest.get("imports")
    if imports is not None:
        if not isinstance(imports, list):
            result.error("'manifest.imports' must be a list")
        else:
            for imp in imports:
                if not isinstance(imp, str):
                    result.error(f"Import entry is not a string: {imp}")
                elif not IMPORT_RE.match(imp):
                    result.error(f"Invalid import format: '{imp}' (expected namespace/crate:tag)")

    return result


def check_image_tag(image: str, timeout: int = 10) -> tuple[str, bool, str]:
    """Check if a docker image tag exists on its registry.

    Returns (image, exists, message).
    """
    image = image.strip()

    # No tag means :latest -- skip check
    if ":" not in image:
        return (image, True, "no tag (implicit :latest)")

    # Parse image into registry/repo:tag
    parts = image.rsplit(":", 1)
    repo_path = parts[0]
    tag = parts[1]

    try:
        if repo_path.startswith("quay.io/"):
            # quay.io/biocontainers/samtools:1.23--h... -> biocontainers/samtools
            repo = repo_path[len("quay.io/"):]
            # Need namespace/name from repo
            repo_parts = repo.split("/", 1)
            if len(repo_parts) != 2:
                return (image, True, "skipped (unusual quay.io path)")
            namespace, name = repo_parts
            url = f"https://quay.io/api/v1/repository/{namespace}/{name}/tag/?specificTag={tag}"
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
                tags = data.get("tags", [])
                if tags:
                    return (image, True, "verified on quay.io")
                else:
                    return (image, False, f"tag not found on quay.io")

        elif "/" in repo_path and not repo_path.startswith("quay.io"):
            # Docker Hub: namespace/repo or library image
            # Could also be other registries like ghcr.io
            if repo_path.startswith("ghcr.io/"):
                return (image, True, "skipped (ghcr.io -- no public API)")

            # Assume Docker Hub for namespace/repo without registry prefix
            repo_parts = repo_path.split("/")
            if len(repo_parts) == 2:
                namespace, name = repo_parts
                url = f"https://hub.docker.com/v2/repositories/{namespace}/{name}/tags/{tag}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        return (image, True, "verified on Docker Hub")
            elif len(repo_parts) >= 3:
                # Unknown registry (e.g., gcr.io/project/image)
                return (image, True, f"skipped (unknown registry)")

            return (image, True, "skipped (could not determine registry)")

        else:
            # Single-name image like "openjdk" -- Docker Hub library
            url = f"https://hub.docker.com/v2/repositories/library/{repo_path}/tags/{tag}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return (image, True, "verified on Docker Hub")
            return (image, False, "tag not found on Docker Hub")

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return (image, False, f"tag not found (HTTP 404)")
        return (image, True, f"skipped (HTTP {e.code})")
    except Exception as e:
        return (image, True, f"skipped (network error: {e})")


def validate_tags(all_images: set[str]) -> dict[str, tuple[bool, str]]:
    """Tier 2: Check all unique images concurrently."""
    results = {}
    # Filter out images without tags (already warned in Tier 1)
    to_check = {img for img in all_images if ":" in img}

    print(f"\nChecking {len(to_check)} unique image tags on registries...")

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(check_image_tag, img): img for img in to_check}
        done = 0
        for future in as_completed(futures):
            done += 1
            image, exists, msg = future.result()
            results[image] = (exists, msg)
            if done % 10 == 0:
                print(f"  Checked {done}/{len(to_check)} images...", file=sys.stderr)

    return results


def print_result(result: ValidationResult, tag_results: dict | None = None):
    """Print validation results for a single manifest."""
    print(f"\n{result.filepath}")
    for msg in result.infos:
        print(f"  OK    {msg}")
    for msg in result.warnings:
        print(f"  WARN  {msg}")
    for msg in result.errors:
        print(f"  ERROR {msg}")


def sort_manifests(files: list[Path]):
    """Sort commands alphabetically by command name in each manifest file."""
    sorted_count = 0
    for filepath in files:
        try:
            text = filepath.read_text()
            data = yaml.safe_load(text)
        except Exception:
            continue

        if not data or "manifest" not in data:
            continue
        commands = data["manifest"].get("commands")
        if not commands or not isinstance(commands, list):
            continue

        # Check if already sorted
        names = [c.get("command", "") for c in commands if isinstance(c, dict)]
        sorted_names = sorted(names, key=str.casefold)
        if names == sorted_names:
            continue

        # Sort commands by name (case-insensitive)
        commands.sort(key=lambda c: str.casefold(c.get("command", "")) if isinstance(c, dict) else "")
        data["manifest"]["commands"] = commands

        # Write back preserving YAML style
        with open(filepath, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        rel = filepath.relative_to(ROOT)
        print(f"  Sorted {rel} ({len(commands)} commands)")
        sorted_count += 1

    print(f"\nSorted {sorted_count} manifests.")


def main():
    check_tags = "--check-tags" in sys.argv
    do_sort = "--sort" in sys.argv

    # Discover manifests
    files = discover_manifest_files(ROOT)

    if do_sort:
        print(f"Sorting commands in {len(files)} manifests...")
        sort_manifests(files)
        return

    print(f"Validating {len(files)} manifests...")

    # Tier 1: Structural validation
    results: list[ValidationResult] = []
    all_images: set[str] = set()

    for filepath in files:
        r = validate_structure(filepath)
        results.append(r)

        # Collect images for Tier 2
        try:
            with open(filepath) as f:
                data = yaml.safe_load(f)
            if data and "manifest" in data:
                for cmd in data["manifest"].get("commands") or []:
                    if isinstance(cmd, dict) and cmd.get("docker_image"):
                        all_images.add(cmd["docker_image"].strip())
        except Exception:
            pass

    # Tier 2: Registry tag verification
    tag_results = None
    if check_tags:
        tag_results = validate_tags(all_images)

    # Print results
    total_errors = 0
    total_warnings = 0
    tag_errors = 0

    for r in results:
        print_result(r, tag_results)
        total_errors += len(r.errors)
        total_warnings += len(r.warnings)

    # Print tag results summary
    if tag_results:
        missing = [(img, msg) for img, (exists, msg) in tag_results.items() if not exists]
        verified = sum(1 for _, (exists, _) in tag_results.items() if exists)
        skipped_imgs = [(img, msg) for img, (exists, msg) in tag_results.items()
                        if exists and "skipped" in msg]

        print(f"\nImage tag verification:")
        print(f"  {verified} verified, {len(missing)} not found, {len(skipped_imgs)} skipped")

        if missing:
            print(f"\n  Missing image tags:")
            for img, msg in sorted(missing):
                print(f"    ERROR {img}: {msg}")
            tag_errors = len(missing)
            total_errors += tag_errors

    # Summary
    total_passed = sum(1 for r in results if r.ok)
    total_failed = len(results) - total_passed
    print(f"\nValidation complete: {total_passed} passed, {total_failed + tag_errors} errors, {total_warnings} warnings")

    if total_errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
