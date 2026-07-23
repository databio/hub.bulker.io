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

## Automated refgenie crate updates

`databio/refgenie` is the **only** crate the refgenie-registry nightly build
activates, so it must be self-contained: every command any refgenie recipe
invokes has to resolve under `bulker activate databio/refgenie` alone. It
imports `bulker/coreutils` internally, because every recipe's version expression
pipes through `grep -aoP` and `awk` and those must not fall through to the
build host.

Its pins are **derived from `bulker/biobase`** rather than discovered
independently — see `update_refgenie_crate.py`, the reviewable source map
`refgenie_crate_sources.yaml`, and `.claude/skills/update-refgenie-crate.md`.
`.github/workflows/scheduled-refgenie-update.yml` runs it **quarterly** (not
weekly like biobase) and always opens a PR: refgenie names each asset after the
tool version that built it, so a pin bump renames published assets, forces a
rebuild and orphans S3 objects.

The interesting part is the **sibling map**. biobase pins `hisat2` but not
`hisat2-build`, `bowtie2` but not `bowtie2-build`, `tabix` but not `bgzip`,
`bismark` but not `bismark_genome_preparation` — and those `-build` commands are
exactly what refgenie uniquely owns. The map declares which biobase package each
one ships in; every mapping must be verified with `apptainer exec <image> which
<command>` before it is trusted.
