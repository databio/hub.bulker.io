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
