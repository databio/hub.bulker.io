# Review a biobase update

This is the second layer of the monthly biobase update. A smaller model
followed `automation/update-biobase.md`, wrote a new versioned biobase
manifest, and opened a pull request. Check every change yourself and keep only
the updates you can verify. Be strict: a bad tag breaks biobase for every
bulker user, while a missed update is found again next month.

## Steps

1. Read `automation/update-biobase.md` for the rules. Let OLD be the highest
   `bulker/biobase_*.yaml` on `origin/$PR_BASE` (sort by version, not as
   text), and NEW the versioned manifest this pull request adds. See what
   changed:

   ```bash
   git diff --name-status origin/$PR_BASE
   git diff origin/$PR_BASE -- bulker/
   diff bulker/biobase_<old>.yaml bulker/biobase_<new>.yaml
   ```

2. Check the files:
   - The only changes are the new file `bulker/biobase_<new>.yaml` and the
     `bulker/biobase.yaml` symlink. OLD and every other manifest are
     untouched.
   - `<new>` is OLD's version with the patch number raised by one, and the
     `version:` field inside NEW matches it.
   - `bulker/biobase.yaml` is still a symlink (`git ls-files -s` shows mode
     `120000`) and points to `biobase_<new>.yaml` (`readlink`).
   - Apart from `version:` and the tags in `docker_image`, NEW is identical to
     OLD: the same commands in the same order, the same fields, the same
     formatting.
3. For each changed `docker_image`, query its registry yourself and check:
   - **Same provider.** Everything before the `:` (registry and repository)
     is unchanged; only the tag differs.
   - **The tag exists.** quay.io:
     `https://quay.io/api/v1/repository/<namespace>/<name>/tag/?specificTag=<tag>`;
     Docker Hub: `https://hub.docker.com/v2/repositories/<namespace>/<repo>/tags/<tag>`.
   - **It is newer than the old pin** by the rules in section 2 of the
     procedure: for biocontainers, a higher version, or the same version with a
     higher build; semantic version order for `broadinstitute/gatk`,
     `broadinstitute/picard`, and `quay.io/xujishu/cellranger` (never below
     `6.0.0`); highest `RELEASE_<major>_<minor>` for
     `bioconductor/bioconductor_docker`.
   - **It is not skipped by the procedure** (`nsheff/pigz`,
     `databio/refgenie`, any `latest` tag).
   - If a newer acceptable tag exists than the one proposed, keep the proposed
     tag but note the newer one in your review.
4. Fix what fails:
   - Set every `docker_image` that fails a check back to OLD's exact value.
   - Fix a wrong `version:` field or symlink target.
   - Restore any other changed file under `bulker/` with
     `git checkout origin/$PR_BASE -- <file>`.
   - If no tag update is left, delete NEW and restore the symlink with
     `git checkout origin/$PR_BASE -- bulker/biobase.yaml`.
   - Do not add updates the pull request did not propose.
5. Write `/tmp/review.md`: one summary sentence; a table with each changed
   image, its old tag, the proposed tag, keep or revert, the reason, and the
   registry URL you checked; and one line each on the version bump, the
   symlink, and whether OLD and all other files are untouched.

When you finish, a hook re-runs `python validate_manifests.py --check-tags`,
commits your changes, and posts your review on the pull request. A person then
merges it. If nothing is left, the hook closes the pull request. If the check
fails, it tells you what to fix. Never commit, push, comment on, merge, or
close the pull request yourself.
