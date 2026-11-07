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
python -m macro_version --check-tag v2.1.0
git tag -a v2.1.0 -m "MacroRunner v2.1.0"
git push origin v2.1.0
```

Replace `2.1.0` in future releases. Never reuse or move a published version
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
