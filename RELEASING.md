# Windows versioning and releases

The package version lives in `src/poketokenbar_windows/__init__.py`. Packaging, client identifiers, the EXE Windows version resource, `build-info.json` and the UI build label derive from it. A build from the exact matching Windows tag displays `vX.Y.Z`; every other build displays `vX.Y.Z-dev` with its short commit. The numeric EXE file version remains the four-part Windows form (for example, `1.0.0.0`), while its string version includes the build label.

- `v0.1.0` identifies the historical Qt Widgets snapshot at `3377ff1db3949fc7d997ae555d373f4c3f4343b6`. It aliases `bruno/ultima-fea-pero-estable-2026-09-01`; no new build or retrospective Release was made.
- Intermediate QML builds are identified by commit SHA.
- `v1.0.0` will identify the first formal QML release, at the merged commit of PR #13. Later `1.x` versions describe this Windows QML line. They do not encode upstream version parity.
- This small experimental repository uses normal Releases and no separate prerelease channel. A Release is useful for a stable download URL, notes and a verifiable ZIP, not required for every development commit.

## First QML Release checklist

1. Review and merge the PR, update local `master`, and verify its HEAD matches `origin/master`. Set `__version__` to the release number **before** merging.
2. Resolve the local tag-name collision: this checkout has upstream's `v1.0.0` tag, while `origin` does not. Preserve upstream's ref under a namespaced local tag if needed, then remove only the local unnamespaced upstream tag. Do not alter upstream's remote tag.
3. Create and push the annotated Windows `v1.0.0` tag on the exact merged commit. Never move a published release tag.
4. Run the project tests and `scripts/build-exe.ps1` from that commit. Verify `build-info.json` contains the tag commit, `version: 1.0.0`, `release: true`, and `display_version: v1.0.0`; verify the EXE version properties match. Check the executable starts with a separate `PTB_STATE_DIR`.
5. ZIP the verified `PokeTokenBar-Windows` directory without rebuilding or changing its contents. Note its SHA-256 and include the checksum with the release notes.
6. Publish a **normal** GitHub Release for the existing tag, attach that exact ZIP and concise change/compatibility notes. GitHub's latest-Release API excludes prereleases and drafts; the app's update checker uses that endpoint.

For later releases, bump the one source version before merging and repeat the exact-tag build and verification. The updater only advises and links to a Release; it never installs or replaces an executable. Review `UPSTREAM.md` for upstream progress independently.
