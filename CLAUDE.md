# CLAUDE.md

## What this is

Registry of bulker crate manifests, hosted at hub.bulker.io. Each namespace folder (e.g. `databio/`, `bulker/`) contains YAML manifest files defining containerized command environments.

## Manifest versioning

- `name_1.0.0.yaml` — versioned manifest (real file, source of truth)
- `name.yaml` → symlink to latest versioned file

**To add/update a crate:**

1. Create or edit the versioned file: `namespace/name_version.yaml`
2. Update the symlink: `ln -sf name_version.yaml namespace/name.yaml`
3. Commit and push to master

## Build and deploy

The site builds and deploys automatically on push to master (GitHub Actions → Cloudflare Workers). No local build needed. The build script (`build_site.py`) runs in CI and generates `docs/` from the source manifests.

## Validation

Run `python validate_manifests.py --check-tags` to validate manifests locally. This also runs in CI before deploy.

## Automated biobase updates

A scheduled GitHub Actions workflow (`.github/workflows/scheduled-biobase-update.yml`) runs every Thursday at midnight UTC. It uses Claude Code with the `.claude/skills/update-biobase.md` skill to:

1. Check all biobase container images for newer tags via registry APIs (Quay.io, Docker Hub)
2. Create a new versioned manifest with updated tags (patch version bump)
3. Open a PR for human review

The workflow can also be triggered manually via `workflow_dispatch`. Some images are intentionally skipped (cellranger, pigz, refgenie) because they use custom registries or pinned versions.
