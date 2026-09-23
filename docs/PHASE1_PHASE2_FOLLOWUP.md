# Phase 1 follow-up and Phase 2 preview

Date: 2026-09-23. Branch: `codex/libby-device-pairing`.

## Decision

The previous session's reproducible Phase 1 defects were repaired. Normal setup
passed with the existing dedicated browser profile and one linked card on macOS
ARM64, both from source and from the standalone binary. Fresh processes reused
the saved identity.
The public-release gate is still open: this is one machine, one account, and one
library. No circulation action was performed.

Phase 2 list import and catalog matching have begun as a preview. The official
2026 Booker longlist example yielded a classification for all 13 items in the
connected library: 10 matched, 3 unmatched, none incomplete. Those categories
are catalog suggestions, not an independent check of title/edition correctness.

## Repairs and evidence

| Area | Change | Check |
| --- | --- | --- |
| Standalone spec | Resolve source paths from `SPECPATH`; include Playwright imports | macOS ARM64 one-file build passed outside checkout |
| Browser packaging | Install `browser` extra in release job; run packaged driver smoke | Frozen runtime check passed without Python/source in its working directory |
| Normal setup | Official-site Chrome profile, browser restart, native card cross-check before credential replacement | Live `setup --timeout 60` passed with one card from source and the binary; fresh binary `cards`, public-title `search`, and `doctor` all passed |
| Credential lifecycle | Versioned token/chip record in one OS credential item; read legacy token; save rotation only after successful sync | Synthetic success/failure tests; natural expiry remains untested |
| Logout | Remove native credential and dedicated profile | Code review and unit checks only; live logout was not run |
| Search resilience | Preserve successful libraries, warn for failed search or availability, stable JSON object | Synthetic multi-library tests; live public-title search passed |
| Card resolution | Reject catalog operations if a linked website ID has no resolved library key | Offline regression test; one-card live path passed |
| Filters/diagnostics | Enum format, unknown library error, nonzero failed `doctor` | Live invalid-key/format exits 2; healthy `doctor` exits 0; offline disconnected exit 2 |
| Package metadata | SPDX license expression | Final local wheel/sdist build passed without license warnings |

The original 31-test baseline grew to 45 passing tests. Ruff and Pyright passed.
The existing account check and public-title search passed outside the sandbox;
account output was suppressed. No card number, token, account payload, or private
library key is included in this report or in committed test fixtures.

## Phase 2 preview

Implemented:

- Local CSV, text, and ISBN list import with row and ISBN validation.
- Direct HTTPS `.csv`, `.txt`, and `.isbn` import. A preview prints a SHA-256
  fingerprint; saving requires the same fingerprint, so changed remote content
  cannot be accepted as the reviewed version.
- SQLite schema version 2 for named lists and ordered items.
- Unicode normalization, title/author scoring, ISBN match, and edition grouping
  across libraries. Results are `matched`, `ambiguous`, `unmatched`, or
  `incomplete` when any library query fails.
- A 13-title CSV transcribed from the
  [official Booker announcement](https://thebookerprizes.com/media-centre/press-releases/longlist-for-booker-prize-2026-rewards-risk).

The live Booker match returned 10 exact title/author scores of 1.0. The three
unmatched titles were **The Shadow of the Object**, **The End of Everything**,
and **May We Feed the King**. Zero catalog-provider errors were observed. The
result remains a catalog snapshot; an unmatched title can reflect publication,
regional catalog, metadata, or search limitations. No availability or patron
eligibility conclusion follows from these match labels.

## Required next-session tests

1. **Packaged first-run:** on a clean macOS user profile with Google Chrome,
   no checkout, Python, or virtualenv, run the released binary's `setup`,
   `cards`, public-title `search`, and `doctor`. Repeat on macOS Intel, Windows,
   and Linux. Record browser launch, credential backend, and restart behavior.
2. **Credential failure paths:** with a disposable profile, close the browser
   during setup and verify the previous credential is unchanged. Test missing
   Chrome and a revoked session. Observe a naturally expired session when
   available; confirm the reconnect instruction and absence of retry loops.
   Live logout should be run only with a disposable profile because it removes
   local session state.
3. **Multiple cards and UI parity:** use two distinct authorized libraries,
   including partner/Advantage cases if available. Compare the same edition,
   format, and card at nearly the same time in official Libby and CLI output.
4. **Phase 2 quality:** inspect the three unmatched Booker titles in official
   catalog UI and manually review representative matched editions. Exercise an
   ambiguous work and an ISBN-only list. Add bounded pagination if the search
   result cap hides plausible candidates.
5. **Distribution:** verify release CI on all four OS targets. Keep the PR in
   draft until the clean-machine and credential gates pass. Only then prepare
   Homebrew/PyPI public-release instructions.

## Reproduction

```bash
uv sync --extra dev --extra browser
uv run pytest
uv run ruff check src tests
uv run pyright --pythonpath .venv/bin/python src
uv build
uv run pyinstaller packaging/pyinstaller/libbyctl.spec --noconfirm
./dist/libbyctl auth browser --check-runtime

libbyctl lists import examples/booker-2026-longlist.csv --name 'Booker 2026'
libbyctl lists match booker-2026 --json
```

Treat `cards --json`, match output with library keys, and the local reading-list
database as personal data. Do not publish raw output from a real account.
