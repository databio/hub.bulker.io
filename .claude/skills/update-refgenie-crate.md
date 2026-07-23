# Update the databio/refgenie crate

Sync `databio/refgenie`'s image pins from `bulker/biobase` and open a PR.

This is the refgenie counterpart to `update-biobase.md`, but it is **derived**
rather than discovered: it does not query registries. biobase's own weekly
updater already does that, and this crate's job is to track biobase, not to
independently drift from it.

## Why this crate is special

`databio/refgenie` is the **only** crate the refgenie-registry nightly build
activates. Until 2026-07 the nightly activated `databio/lab,databio/refgenie:1.0.0`;
bulker resolves collisions first-listed-wins, so `databio/lab` -> `bulker/biobase`
silently shadowed 10 of refgenie's 16 commands, and the refgenie manifest stopped
describing what actually built the published assets. Making refgenie
self-contained fixed that, and this updater keeps the two from re-diverging.

Two consequences shape everything below:

- **The crate must be self-contained.** Every command any refgenie-registry
  recipe invokes must resolve under `bulker activate databio/refgenie` alone.
  It imports `bulker/coreutils` internally (recipes' version expressions pipe
  through `grep -aoP` and `awk`), but nothing else is layered on at activation.
- **A pin change is expensive.** refgenie names an asset after the tool version
  that built it, so bumping a pin renames published assets, forces a rebuild,
  and orphans S3 objects. Hence quarterly cadence and PR-only.

## Process

### 1. Review the diff

```bash
python update_refgenie_crate.py --verify-siblings
```

This prints the resolution for every command, the pin diff, and the version
diff. Nothing is written.

### 2. Understand the sibling map

`refgenie_crate_sources.yaml` resolves each command with this precedence:

1. biobase defines the exact command -> use biobase's image
2. biobase defines the declared `sibling_of` package -> use that package's image
3. an `overrides` entry -> use its pinned image

Step 2 exists because the commands refgenie uniquely owns are exactly the ones
biobase does not name: biobase pins `hisat2` but not `hisat2-build`, `bowtie2`
but not `bowtie2-build`, `bowtie` but not `bowtie-build`, `tabix` but not
`bgzip`, `bismark` but not `bismark_genome_preparation`. A naive copy-from-biobase
misses precisely the stale, broken entries.

**Never add a sibling mapping without verifying it empirically.** A conda package
shipping a companion binary is an assumption. `--verify-siblings` prints the
exact commands:

```bash
apptainer exec docker://quay.io/biocontainers/bowtie2:2.5.5--ha27dd3b_0 which bowtie2-build
```

Record the check date in the map's `verified:` field.

### 3. Write the new manifest

```bash
python update_refgenie_crate.py --write --version <next>
```

Use a **minor** bump (1.0.0 -> 1.1.0). Never mutate an existing version in
place: the previous version is the rollback target for the nightly.

Do **not** repoint `databio/refgenie.yaml`. Moving the symlink switches every
`:default` consumer; that is a separate, conscious decision.

### 4. Check every changed tool's version expression still parses

For each tool whose version changed, run its recipe's `custom_seek_keys.version`
expression inside the new image. A tool that reports an empty version does not
fail loudly — it produces a garbage asset name. bowtie2 2.4.1 shipped for years
printing `bowtie2-build-s version ` with nothing after it, and only produced a
plausible asset name because `grep -aoP` accidentally matched a compiler
debug-prefix-map path fragment further down the output.

### 5. Check crate coverage

Run `refgenie-registry/tools/check_crate_coverage.py` against the new manifest.
It re-derives the required command set from `recipes/*/recipe.yaml` and fails if
the crate no longer covers it.

### 6. Open a PR, never auto-merge

The PR body must call out which changed tools appear in
`refgenie-registry/pep/samples.csv` — those are the ones that cost a rebuild.

## Automation

`.github/workflows/scheduled-refgenie-update.yml` runs this quarterly (Jan/Apr/Jul/Oct 1)
and on `workflow_dispatch`. It runs the script deterministically and opens a PR.
