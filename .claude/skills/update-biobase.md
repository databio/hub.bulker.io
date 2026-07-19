# Update biobase manifest

Check all container images in the biobase manifest for newer tags and create a PR with updates.

## Process

### 1. Find the current manifest

Look for the latest versioned biobase manifest in `bulker/`:

```bash
ls bulker/biobase_*.yaml | sort -V | tail -1
```

Read this file to get the current commands and image tags.

### 2. Check each image for updates

For each command entry, query the container registry API to find the latest available tag.

**Skip these entries** (pinned or custom registries):
- `nsheff/pigz` — custom image, no registry API
- `databio/refgenie` — custom image, uses `latest` tag
- Any image using the `latest` tag

`quay.io/xujishu/cellranger` is NOT skipped: it is a normal quay.io repo and
answers the same tag API as the biocontainers images below. Tags older than
6.0.0 are stored as Docker v1 manifests, which apptainer cannot convert, so
never move this entry backwards below 6.0.0.

**For quay.io/biocontainers images:**

```bash
curl -s "https://quay.io/api/v1/repository/biocontainers/<tool>/tag/?limit=100&onlyActiveTags=true"
```

Parse the JSON response. Tags follow the pattern `<version>--<hash>_<build>`. To find the latest:
1. Filter out tags named `latest`
2. Sort by semantic version of the version prefix (the part before `--`)
3. Among tags with the same version, prefer higher build numbers
4. Pick the tag with the highest version

**For `quay.io/xujishu/cellranger`:**

```bash
curl -s "https://quay.io/api/v1/repository/xujishu/cellranger/tag/?limit=100&onlyActiveTags=true"
```

Tags here are plain semantic versions (`3.1.0`, `6.0.0`, `6.0.1`) — NOT the
biocontainers `<version>--<hash>_<build>` pattern. Sort by semantic version and
pick the highest. Ignore any tag below 6.0.0: those are Docker v1 manifests
(`application/vnd.docker.distribution.manifest.v1+prettyjws`) that apptainer
cannot convert, so selecting one silently breaks every apptainer-based consumer.

**For Docker Hub images** (broadinstitute/*, bioconductor/*):

```bash
curl -s "https://hub.docker.com/v2/repositories/<namespace>/<repo>/tags/?page_size=100&ordering=last_updated"
```

For `broadinstitute/gatk`: pick the latest tag matching `<major>.<minor>.<patch>.<build>` pattern (semantic version sort).
For `broadinstitute/picard`: pick the latest tag matching `<major>.<minor>.<patch>` pattern.
For `bioconductor/bioconductor_docker`: pick the latest `RELEASE_<major>_<minor>` tag (highest major, then highest minor).

**For UCSC tools** (quay.io/biocontainers/ucsc-*):

These all use version numbers like `482--h0b57e2e_0`. Check for updates using the same quay.io API as other biocontainers.

### 3. Compare and decide

For each image, compare the current tag with the latest available:
- If the latest tag is different and represents a newer version, mark it for update
- Log each comparison result (tool name, current tag, latest tag, update needed)
- Present a summary table before making changes

### 4. Create the updated manifest

If any updates are found:

1. **Determine the new version.** Bump the patch version of the current manifest (e.g., `0.1.0` -> `0.1.1`). Use minor bump only if tools are added or removed.

2. **Create the new manifest file.** Copy the current manifest to `bulker/biobase_<new_version>.yaml`. Update the `version:` field in the YAML. Replace updated image tags.

3. **Update the symlink** (if one exists): `ln -sf biobase_<new_version>.yaml bulker/biobase.yaml`

4. **Do NOT delete the old versioned manifest.** Keep it for reference.

### 5. Commit and open a PR

```bash
git checkout -b biobase-update-<new_version>
git add bulker/biobase_<new_version>.yaml bulker/biobase.yaml
git commit -m "Update biobase to <new_version>

Updated images:
- <tool1>: <old_tag> -> <new_tag>
- <tool2>: <old_tag> -> <new_tag>
..."
git push -u origin biobase-update-<new_version>
```

Open a PR with:
- Title: `Update biobase to <new_version>`
- Body: summary table of all updated images, plus a note about any images that were skipped or had no updates

### 6. If no updates found

If all images are already at their latest versions, do not create any files or PRs. Just report that everything is up to date.

## Important rules

- **Same providers, just new tags.** Never switch an image from one registry to another. Only update the tag.
- **Preserve all other fields.** Keep `docker_command`, `docker_args`, `description`, and any other fields exactly as they are.
- **Preserve YAML formatting.** Match the indentation and style of the existing manifest.
- **Be conservative.** If you can't determine which tag is newer, skip that entry.
