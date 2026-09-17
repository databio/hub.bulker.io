# Update the biobase manifest

This is the canonical procedure for recurring biobase container updates. Any
agent or automation that performs this task must follow this file completely.

## Goal

Check all container images in the latest versioned biobase manifest for newer
tags. If verified updates exist, create the next versioned manifest, update the
`bulker/biobase.yaml` symlink, and prepare a pull request for human review.

If no verified updates exist, make no repository changes and create no pull
request.

## Before starting

Check whether there is already an open pull request for a biobase update whose
head branch starts with `biobase-update-`.

- If one exists and the execution environment can safely continue that branch,
  start from that branch and preserve all valid unmerged changes already there.
- If one exists but the execution environment cannot safely continue it, make no
  changes and stop rather than creating a competing update PR.
- Otherwise start from the current `master` branch.

Never discard valid unmerged biobase changes from an existing update PR.

## 1. Find the current manifest

Find the latest versioned biobase manifest in `bulker/`:

```bash
ls bulker/biobase_*.yaml | sort -V | tail -1
```

Read this file to get the current commands and image tags.

## 2. Check each image for updates

For each command entry, query the container registry API to find the latest
available tag.

### Skip rules

Skip these entries:

- `nsheff/pigz` — custom image, no registry API
- `databio/refgenie` — custom image, uses `latest` tag
- Any image using the `latest` tag

`quay.io/xujishu/cellranger` is **not** skipped. It is a normal quay.io repo and
uses the tag API described below. Tags older than `6.0.0` are stored as Docker
v1 manifests that Apptainer cannot convert, so never move this entry backwards
below `6.0.0`.

### quay.io/biocontainers images

Query:

```bash
curl -s "https://quay.io/api/v1/repository/biocontainers/<tool>/tag/?limit=100&onlyActiveTags=true"
```

Tags follow the pattern `<version>--<hash>_<build>`.

To select the latest acceptable tag:

1. Filter out tags named `latest`.
2. Pick the highest version prefix, meaning the part before `--`.
3. Among tags at that version, pick the highest `_<build>`.
4. A different hash at a higher build is a rebuild, not a variant; take it.
5. Never move to a lower version or build than the current pin.

Some tools publish parallel `pyXXX` builds at the same version and build
number. Those are ties; take the highest `pyXXX`.

### `quay.io/xujishu/cellranger`

Query:

```bash
curl -s "https://quay.io/api/v1/repository/xujishu/cellranger/tag/?limit=100&onlyActiveTags=true"
```

Tags are plain semantic versions such as `3.1.0`, `6.0.0`, and `6.0.1`; they do
not use the biocontainers `<version>--<hash>_<build>` pattern.

Sort by semantic version and select the highest tag, but ignore every tag below
`6.0.0`. Those older tags are Docker v1 manifests
(`application/vnd.docker.distribution.manifest.v1+prettyjws`) and selecting one
breaks Apptainer-based consumers.

### Docker Hub images

For `broadinstitute/*` and `bioconductor/*`, query:

```bash
curl -s "https://hub.docker.com/v2/repositories/<namespace>/<repo>/tags/?page_size=100&ordering=last_updated"
```

Selection rules:

- `broadinstitute/gatk`: select the latest tag matching
  `<major>.<minor>.<patch>.<build>` using semantic-version ordering.
- `broadinstitute/picard`: select the latest tag matching
  `<major>.<minor>.<patch>` using semantic-version ordering.
- `bioconductor/bioconductor_docker`: select the latest
  `RELEASE_<major>_<minor>` tag by highest major, then highest minor.

### UCSC tools

For `quay.io/biocontainers/ucsc-*`, use the same quay.io API and selection rules
as other biocontainers images. These commonly use versions such as
`482--h0b57e2e_0`.

## 3. Compare and decide

For every image:

- compare the current tag with the latest acceptable tag;
- update only when the latest tag is demonstrably newer;
- never downgrade;
- log the tool name, current tag, latest tag, and whether an update is needed.

Present a summary table before making changes.

If it is unclear which tag is newer or whether a candidate is safe, leave that
entry unchanged.

## 4. Create the updated manifest

If at least one verified update exists:

1. Determine the new manifest version. Bump the patch version of the current
   manifest, for example `0.1.0` -> `0.1.1`. Use a minor bump only when tools are
   added or removed.
2. Copy the current manifest to `bulker/biobase_<new_version>.yaml`.
3. Update the `version:` field in the new YAML file.
4. Replace only the verified image tags that need updating.
5. Update the symlink, if present:

   ```bash
   ln -sf biobase_<new_version>.yaml bulker/biobase.yaml
   ```

6. Do **not** delete the previous versioned manifest.

## 5. Validate the result

Run the repository's manifest validation before publication:

```bash
python validate_manifests.py --check-tags
```

Do not publish a pull request if validation fails. Fix only problems caused by
this update; do not broaden the task into unrelated repository cleanup.

## 6. Prepare the review change

Use branch name:

```text
biobase-update-<new_version>
```

Commit message:

```text
Update biobase to <new_version>

Updated images:
- <tool1>: <old_tag> -> <new_tag>
- <tool2>: <old_tag> -> <new_tag>
...
```

The pull-request title must be:

```text
Update biobase to <new_version>
```

The pull-request body must contain all three sections, even when one is empty:

```markdown
## Updated

| Tool | Old tag | New tag |
|---|---|---|

## Checked, no update needed

Every other image, with the tag you confirmed is current.

## Skipped

Each skipped image and the rule that skipped it.
```

Use the execution environment's native branch and pull-request publication
mechanism when it provides one. Do not duplicate that mechanism with manual
`git push` or `gh pr create` calls when the environment will publish the branch
or PR itself.

If the environment does not publish changes automatically but authenticated git
and GitHub tooling are available, create the branch, commit the changes, push the
branch, and open the PR using the specification above.

Never merge the pull request automatically.

## 7. If no updates are found

If every applicable image is already at its latest acceptable version, do not
create a new manifest, branch, commit, or pull request. Report that everything
is up to date.

## Invariants

- **Same providers, only newer tags.** Never switch an image from one registry
  or repository to another.
- **Never downgrade.** A candidate must be demonstrably newer than the current
  pin.
- **Preserve all unrelated fields.** Keep `docker_command`, `docker_args`,
  `description`, and every other unrelated field exactly as it is.
- **Preserve YAML formatting.** Match the indentation and style of the current
  manifest.
- **Be conservative.** If a candidate cannot be verified confidently, skip it.
- **Keep old versioned manifests.** Never replace or delete historical versions.
- **No duplicate update PRs.** Continue an existing biobase update when safe;
  otherwise stop rather than competing with it.
