# Releasing MacroRunner

Versions follow MAJOR.MINOR.PATCH. A bug-fix release increases PATCH; a
backward-compatible feature release increases MINOR; a compatibility-breaking
release increases MAJOR. Existing macro JSON's `version: 2` is a **file format
version**, independent of the application version.

## Single source of truth

Edit `[project].version` in `pyproject.toml` when preparing a release.
Do **not** hardcode a separate version in `installer.iss`.

`python -m macro_version` prints the project version. The Ubuntu
`packaging/build-deb.sh` reads it from the same module; CI passes it to
Inno Setup as `/DMyAppVersion=<version>`. PyInstaller includes installed
distribution metadata so **Help → About MacroRunner** shows the same version
in Windows and Ubuntu packaged applications, as well as pipx installs.

## Prepare a release

1. Merge the relevant feature and fix PRs into `main`.
2. Update `CHANGELOG.md` with accurate changes and replace the pending
   release heading with the release date.
3. Bump `pyproject.toml` if necessary. Use `python -m macro_version` to
   verify the intended version. Run the full automated tests on both platforms.
4. Manually test a packaged build on Ubuntu 24.04 (X11 preferred) and Windows,
   including mouse capture, keyboard input, region monitoring, pause/stop,
   window visibility, and permissions. CI's offscreen smoke tests cannot
   guarantee real desktop behavior.
5. Merge release preparation changes. No release is published by merging.

## Publish only when QA is approved

From an up-to-date `main` checkout, create and push an annotated tag:

```bash
git checkout main
git pull --ff-only origin main
python -m macro_version --check-tag v2.4.0
git tag -a v2.4.0 -m "MacroRunner v2.4.0"
git push origin v2.4.0
```

Replace `2.4.0` in future releases. Never reuse or move a published version
tag; make a new patch version instead.

The tagged **Build desktop installers** workflow validates that the tag matches
`pyproject.toml`, reruns the test suite on Ubuntu and Windows, builds both
native packages, and checks packaged startup. Only after all jobs succeed does
it publish a GitHub Release with both files:

- `macrorunner_<version>_amd64.deb`
- `MacroRunner-Setup-<version>.exe`

A mismatched tag fails validation and **cannot publish**. PR and normal
`main` builds continue to upload temporary Actions artifacts but do not
publish GitHub Releases.

## Notes

The Ubuntu package currently targets Ubuntu 24.04 amd64; Windows builds target
x64. Windows binaries are unsigned, so SmartScreen may warn. Signing and
broader platform QA are separate release-readiness decisions. Keep the existing
Windows installer AppId unchanged across updates so upgrades work.

## Manual publication while CI is disabled

For v2.4.0 the maintainer has accepted the completed roadmap and reported successful complex workflow testing. This is not evidence that every desktop QA case or hosted CI job passed. Before publishing, build and smoke-test the current native Windows and Ubuntu installers, including upgrade and version metadata. Record any remaining exceptions; Ubuntu desktop automation is X11-only, and covered/minimized background input is not supported. Use Ubuntu 24.04 amd64 for the documented package target.

Build both packages locally from the same clean release commit using [installation instructions](installation.md). Verify the version using `python -m macro_version --check-tag v2.4.0`. Once the maintainer approves publication, create the matching annotated tag (only if unused) as above while workflows remain disabled. Draft a GitHub Release for that tag, attach `MacroRunner-Setup-2.4.0.exe` and `macrorunner_2.4.0_amd64.deb`, document X11-only Linux support and unsigned Windows installer status, then publish. Do not represent deferred CI or untested platform cases as passing. Never re-enable workflows without explicit approval.
