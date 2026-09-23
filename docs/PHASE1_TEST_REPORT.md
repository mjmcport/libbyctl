# Phase 1 validation report and handoff

Date: 2026-09-23. Application revision: `0bbc8c2` on `codex/libby-device-pairing`.
Environment: macOS ARM64, Python 3.12.9, existing user-authorized credential in macOS Keychain.
Scope: Phase 0 packaging and Phase 1 read-only account/catalog behavior from `docs/PLAN.md`.

## Decision

The source-based tool is usable for this account's read-only discovery workflow.
Phase 1 is **not release-complete**: first-run setup/distribution and durable
authentication remain blockers. Do not begin Phase 2 on the assumption that the
public-release acceptance criteria are satisfied.

This round made no account/circulation changes and did not log out, reset the
browser, overwrite credentials, or modify production application code. It added
five offline service tests and this report. Database/config checks used temporary
directories. Raw account payloads, card identifiers, library identifiers, and
credentials are omitted from committed artifacts.

## Executed checks

| Area | Result | Evidence/limits |
| --- | --- | --- |
| Unit suite | PASS | 31 tests; up from 26 with five additional service tests |
| Coverage | MEASURED | 67% statements overall; search service 100%. Live subprocess checks are not included in this coverage figure |
| Ruff / Pyright | PASS | No lint or source type-check errors |
| Existing saved authentication | PASS | Fresh process `auth status`, no browser required |
| Card discovery | PASS | One card, one resolved library; all synchronized website IDs resolved |
| Counts and limits | PASS for mapping | Mapped fields equal the raw card counts/limits |
| Card output | PASS | JSON parses and excludes raw response; human output did not expose full card ID |
| Title search | PASS | “The Hobbit”, two results, both availability objects populated |
| Author filtering | PASS | Tolkien filter returns results; impossible author returns empty array |
| Ebook / audiobook filtering | PASS | Each returns only the requested format in sampled results |
| ISBN lookup | PASS | ISBN taken from a catalog result retrieves that same title ID |
| Specific-library filter | PASS | Results restricted to the sole linked library |
| Nonexistent title | PASS | Exit 0, valid empty JSON array |
| Unknown library key | GAP | Exit 0, empty array; indistinguishable from no matching books |
| Invalid format | PARTIAL | Exit 2 observed, but code forwards arbitrary format strings to provider; not local enum validation |
| Invalid result limit | PASS | `--per-library 0` rejects with exit 2 |
| Missing credentials | PASS | Process-local blank token override gives exit 2 and clean error, no traceback |
| Local initialization | PASS | Creates database and config in isolated temporary directory |
| Healthy doctor | PASS | Initialized diagnostic output contains no failed checks |
| Disconnected doctor | GAP | Displays failed credential check but exits 0 |
| Availability mapping | PASS for sampled API contract | Copies, holds, wait days map to corresponding response fields; this is not independent UI validation |
| Multiple libraries / sorting | PASS in synthetic tests | Concurrent results ordered available-first then shortest wait; one real library cannot validate real multi-card behavior |
| Availability endpoint failure | PASS in synthetic test | Result retained with unknown availability |
| Whole-library search failure | GAP confirmed synthetically | One provider exception aborts the entire search rather than returning successes from other libraries |
| Wheel and sdist | PASS | Current revision builds; setuptools emits existing license-metadata deprecation warnings |
| Wheel outside checkout | PASS | Isolated installation and top-level help smoke test |
| Unmodified standalone spec | FAIL | Source script resolved relative to spec directory, producing nonexistent `packaging/pyinstaller/src/libbyctl/__main__.py` |
| Temporary path-corrected binary | PARTIAL PASS | Builds on this Mac; `version` and saved-session `cards --json` succeed |
| Browser auth in that binary | FAIL | Exit 2: browser dependency absent; suggests `uv sync`, which is inappropriate for a standalone-binary user |

The initial live matrix had 19 checks: 17 passes after correcting the count-test
oracle, and two behavior gaps (unknown library, disconnected doctor). Additional
ISBN, impossible-author, packaging, and synthetic failure checks are reported
separately rather than folded into an inflated pass count. Successful sampled
searches took approximately 1.5–1.9 seconds; this is not a performance benchmark.

### Corrected count-test assumption

Comparing `len(sync.loans)` directly to a card's reported loan count initially
failed. The response includes an additional magazine entry, while our displayed
count correctly copies `card.counts.loan`. That is not evidence of a mapper bug.
Keep the raw card counters as the mapping oracle; independently confirm their
product meaning in the official UI before using them for Phase 3 capacity logic.

### Build-only accommodations

The repository spec was not edited. A temporary copy replaced its source and
search paths with absolute checkout paths so additional packaging checks could
continue. PyInstaller cache was redirected to a temporary directory after a
sandbox permission error. The resulting one-file executable needed execution
outside sandbox semaphore restrictions. Those environment errors are distinct
from the reproducible spec-path and missing-browser-dependency defects.

## Prioritized work for the next session

1. **P1 — Repair standalone distribution.** Resolve paths from `SPECPATH`/the
   repository root in `packaging/pyinstaller/libbyctl.spec`. The release workflow
   currently installs only the `dev` extra, and the browser module is loaded via
   `importlib`; explicitly package the optional browser runtime and its driver,
   or choose a supported external-browser installation design. A successful
   PyInstaller build is not evidence of working browser login. Retest without a
   source checkout, virtualenv, or Python installed.
2. **P1 — Integrate browser sign-in into normal setup.** The documented/default
   `setup` still takes the unsuccessful direct-pairing path. Make normal setup
   guide the user through the validated browser path, detect missing Chrome,
   handle cancellation, and give standalone-appropriate instructions. Reconcile
   README and Phase 1 acceptance steps with the shipped behavior.
3. **P1 — Finish credential lifecycle.** Existing clients restore only a token,
   not chip state; long-term renewal remains unverified. Define renewal versus
   browser reconnection, persist rotations atomically, and test restart after
   expiry/revocation. Keep good credentials if a replacement attempt fails.
   Define logout for both native credentials and the dedicated browser profile.
4. **P2 — Make partial failures explicit.** A single library search failure must
   not silently discard successes. Decide the JSON envelope, warnings and exit
   semantics; distinguish unavailable metadata from zero availability. Current
   tests characterize the abort behavior rather than endorsing it.
5. **P2 — Validate filters and diagnostics locally.** Reject unknown library
   keys with an actionable error and valid choices; validate format enum before
   account/network access. Decide whether `doctor` returns nonzero for failed
   required checks (recommended) or document that exit status is informational.
6. **P2 — Validate multiple-card and patron-specific behavior.** Use at least
   two libraries, including duplicate/partner/Advantage cards where available.
   Compare card resolution, eligibility and availability against the official
   UI; successful public catalog requests do not prove personalized access.

## Reproduction commands

Run from the checkout of this branch. Agents should apply local RTK command
prefix instructions. These examples are ordinary user shell commands.

```bash
uv sync --extra dev --extra browser
uv run pytest --cov=libbyctl --cov-report=term-missing
uv run ruff check src tests
uv run pyright --pythonpath .venv/bin/python src

uv run libbyctl auth status
uv run libbyctl cards
uv run libbyctl cards --json
uv run libbyctl search "The Hobbit" --per-library 2 --json
uv run libbyctl search "The Hobbit" --author Tolkien --per-library 2 --json
uv run libbyctl search "The Hobbit" --format ebook --per-library 2 --json
uv run libbyctl search "The Hobbit" --format audiobook --per-library 2 --json
uv run libbyctl search "zzzxqnonexistenttitle749102" --json

# Process-only override; does not delete the saved credential.
LIBBYCTL_TOKEN=' ' uv run libbyctl cards

uv build
# Known failure until the spec's paths are corrected:
uv run pyinstaller packaging/pyinstaller/libbyctl.spec --noconfirm
```

Treat `cards --json` as personal data: inspect locally, not in public CI logs or
committed fixtures. Use the public title above for searches rather than printing
the user's borrowed titles. Do not run logout/reset or borrow/hold/return actions
as part of this read-only audit.

To reproduce diagnostic exit behavior without altering normal config/database:

```bash
phase1_tmp=$(mktemp -d)
LIBBYCTL_CONFIG="$phase1_tmp/config.toml" LIBBYCTL_DATA_DIR="$phase1_tmp/data" uv run libbyctl init
LIBBYCTL_CONFIG="$phase1_tmp/config.toml" LIBBYCTL_DATA_DIR="$phase1_tmp/data" LIBBYCTL_TOKEN=' ' uv run libbyctl doctor
echo "$?"
```

Expected current result: failed credential check displayed, exit code 0. Desired
behavior must be agreed before converting this finding to an acceptance test.

## Outstanding acceptance matrix

| Scenario | Setup | Required evidence |
| --- | --- | --- |
| New-user install | Clean VM, no Python or source checkout | Packaged tool opens supported browser and connects through ordinary setup |
| Multiple libraries | User-authorized account with 2+ distinct libraries | Every card resolves; scoped/unscoped searches agree; no silent omissions |
| Availability/UI parity | Same title, edition, format and library at same time | Available copies, holds, wait and eligibility agree or differences are documented |
| Renewal | Naturally expired test session or controlled mock clock plus later real test | Reconnect/refresh works without corruption or retry loops |
| Revocation/logout | Disposable test profile; explicit authorization before removal | Native and browser cleanup behave as documented; unrelated devices unaffected |
| Cancelled login | Disposable profile, close browser before completion | Clean exit; no replacing a previously good credential |
| Missing Chrome | Clean VM or controlled launcher mock | Actionable installation guidance, no traceback |
| Catalog/network outage | Mock transport, not deliberate live overload | Bounded timeout; useful partial results and explicit failed-library status |
| Platform support | macOS Intel/ARM64, Windows, Linux | Installed artifact smoke + credential backend + first-run browser test |
| Machine-readable contract | Captured synthetic success/error/partial fixtures | Stable JSON, no presentation text or secrets mixed into stdout |

The release gate is the complete Phase 1 workflow on a clean machine, not merely
the 31-test result or a working session on the developer's Mac. Keep PR #1 in draft
while P1 blockers remain. The next session should read this report and
`docs/AUTHENTICATION_RESEARCH.md`, reproduce blockers, then implement fixes with
focused regression tests; do not repeat speculative device pairing.
