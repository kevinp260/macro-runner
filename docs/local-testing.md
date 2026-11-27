# Local test procedure and release gates

**Temporary policy — 2026-11-10.** This is the agreed way to test MacroRunner while GitHub Actions are suspended for billing reasons. It is a *temporary replacement for hosted automated checks*, **not** a replacement for real Windows/Ubuntu desktop and installer QA.

## GitHub Actions status and safety

- GitHub-hosted Actions minutes are exhausted until the **2026-12-01** billing reset. **Do not trigger, re-run, or re-enable Actions without explicit user approval, even after that date.** The date is not an automatic restart.
- The unchanged workflow files remain in Git: `.github/workflows/python-checks.yml` (Python checks, Ubuntu/Windows) and `.github/workflows/installers.yml` (Ubuntu/Windows installer builds and smoke checks). Their `push`, `pull_request`, tag, and manual triggers would consume minutes if enabled.
- Workflows are intended to be **disabled through GitHub Actions settings**, not deleted or stripped of triggers. A GitHub code-only PR cannot confirm their current enabled/disabled state; verify under **Repository → Actions** before work that could otherwise trigger CI.
- Use focused branches and PRs. The user reviews/merges; do not auto-merge. Do not remove required branch-protection checks without discussing it with the user.

## Automated tests run manually on the user's machine

Running `unittest` locally is still **automated unit/regression testing**; only its **invocation and reporting** are manual. This process is separate from the later human-performed desktop acceptance checks.

The user currently runs tests on **Ubuntu** in an existing repository checkout with `.venv-tests` and test dependencies installed. Run commands from the repository root. Update to the exact feature branch before testing.

```bash
git fetch origin
git switch <feature-branch>
git pull --ff-only

source .venv-tests/bin/activate
export QT_QPA_PLATFORM=offscreen
export PYTHONPATH="$PWD/tests:$PWD"
```

Run changed-area modules first (replace with relevant module names, as specified in the PR):

```bash
python -u -X faulthandler -m unittest test_qt_region -v
python -u -X faulthandler -m unittest test_qt_properties -v
```

Then run the **full regression suite with one fresh Python process per test module**:

```bash
failed=0

for file in tests/test_*.py; do
    module=$(basename "$file" .py)
    echo "========== $module =========="
    if ! python -u -X faulthandler -m unittest "$module" -q; then
        echo "FAILED: $module"
        failed=1
        break
    fi
done

if [ "$failed" -eq 0 ]; then
    echo "All test modules passed individually."
else
    echo "Full regression failed. Review the module named above."
fi
test "$failed" -eq 0
```

Use separate invocations **instead of** one all-in-one `unittest discover` process on this Ubuntu Qt-offscreen setup: multiple Qt modules in one process have previously caused unreliable X11/Qt teardown. **Do not mark tests green based only on elapsed time or warning counts.** Look for each module's `OK` and a final zero exit code; any `FAILED`, `ERROR`, abort, or nonzero exit code must be investigated. A test report should name the tested branch/commit, OS and modules, including failures or warnings.

### Known local offscreen warnings

While `test_qt_region` passes, Qt can print `This plugin does not support raise()`; `pyscreeze` can report unclosed `which scrot` subprocess pipes; and Xlib sockets can emit `ResourceWarning` at interpreter shutdown. These are **nonfatal only when the module finishes with `OK` and exit code 0**. Do not hide all warnings or interpret them as proof that screenshots work on a real desktop. Investigate if they become test failures or affect real app usage.

### Windows

When a Windows Python test environment is available, run the same modules individually (PowerShell, from repository root):

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONPATH = "$PWD\tests;$PWD"

Get-ChildItem tests -Filter 'test_*.py' | ForEach-Object {
    Write-Host "========== $($_.BaseName) =========="
    python -u -X faulthandler -m unittest $_.BaseName -q
    if ($LASTEXITCODE -ne 0) {
        throw "FAILED: $($_.BaseName)"
    }
}
Write-Host 'All test modules passed individually.'
```

Use a Windows virtual environment with project/test dependencies installed. **This document does not claim that Windows tests have been run yet.**

## For each new issue / PR

1. Assistant makes only scoped changes and adds relevant tests, without invoking GitHub Actions.
2. Assistant provides the exact focused test modules for the PR; the user runs them locally and reports results.
3. User runs the per-module full regression command above before the PR is declared ready. Note the exception explicitly if a checkpoint intentionally defers that full run.
4. Record the evidence on the PR (platform, focused results, full regression result, known warnings). Only then mark PR **Ready for review**; user performs the merge.
5. Real screenshot/input hooks, targeting, global shortcuts, DPI/multi-monitor, and installed app behavior **cannot be signed off by offscreen tests**. Track and perform them through [Issue #64](https://github.com/kevinp260/macro-runner/issues/64) and [docs/manual-tests.md](manual-tests.md).

## Roadmap closure and release handoff (2026-11-27)

The maintainer approved closing the completed v2.2–v2.4 roadmap and QA backlog and requested a consolidated v2.4.0 release after successful complex workflow use. Previously reported Ubuntu X11 checks included region selection, image capture, window targeting, Pause/Stop, global shortcuts and monitoring preview. Earlier local isolated-module regressions were reported passing. These reports do not certify every unchecked case in #64, the latest native Windows installer, multi-monitor/mixed-DPI scenarios, upgrades, or hosted CI. The remaining checks are deferred, not marked passed.

Before publishing, build the Windows and Ubuntu packages from the same release commit, verify install/startup, version metadata and upgrade/persistence, and smoke-test actual desktop automation. Wayland desktop automation remains unsupported; Ubuntu package target is 24.04 amd64/X11. See [release process](releasing.md) for manual publication without Actions. Do not re-enable Actions without explicit maintainer approval, even after billing reset.
