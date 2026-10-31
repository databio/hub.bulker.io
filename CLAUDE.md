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

The complete biobase update procedure lives in
`automation/update-biobase.md`. Recurring runs are handled by a native Jules
Scheduled Task. `AGENTS.md` and `.claude/skills/update-biobase.md` are thin
pointers to that canonical procedure.

`.github/workflows/scheduled-biobase-update.yml` is retained as a manual
`workflow_dispatch` fallback using Claude Code. There should be only one
recurring scheduler for this task.

## databio/refgenie is no longer synced

The refgenie-registry nightly no longer activates `databio/refgenie`: refgenie
now runs each recipe's own container image (the recipe's `docker_image`) with
Docker or Apptainer, so the recipe is the only record of which image builds an
asset, and the registry keeps those pins fresh itself. The crate's quarterly
updater (`update_refgenie_crate.py`, its source map and workflow) is gone. The
`databio/refgenie_*.yaml` manifests stay, for anyone who still activates them,
but nothing updates their pins.
