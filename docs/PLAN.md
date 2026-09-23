# libbyctl implementation and distribution plan

Updated: 2026-09-23

## Current status (2026-09-23)

Phase 1 works for one connected account on macOS and the source CLI has passed
read-only account/catalog checks. Normal setup now uses official-site browser
sign-in and a native account cross-check. Standalone packaging, diagnostics,
and partial-search handling have been repaired and are undergoing smoke tests.
The public-release gate remains open for clean-machine sign-in, naturally
expired credentials, multiple cards, and Windows/Linux/Intel platform checks.

Phase 2 has begun as a preview: CSV/text/ISBN import, reviewed direct-file URL
import, normalization, work/edition grouping, and explicit match states. The
13-title 2026 Booker example received a result for every entry in the connected
library, but match quality and absent titles still need independent review.

Phase 3 now has persistent read-only plans and refresh. A live one-card check
classified the 13-title example and saved/refreshed it in an isolated database.
Phases 4–5 have a simulated, provider-neutral circulation engine with confirmation,
fresh-state checks, and durable retry reconciliation, but no live write adapter.
Research found an unofficial private Libby circulation path using a regular linked
account; see `docs/PRIVATE_CIRCULATION_RESEARCH.md`. Phases 6–7 have a sourced-record registry and catalog comparison, with
no published eligibility records until location and official terms are verified.
Phase 8 has aggregate JSON and an optional read-only local MCP stdio server;
the HTTP API, Home Assistant-specific setup, and `odmpy` trigger remain open.
See `docs/PHASE3_TO_PHASE8_PROGRESS.md` for test evidence and remaining gates.

## Product direction

`libbyctl` is not a downloader. It is the discovery, planning, and circulation-control layer for a user's Libby libraries. Download workflows such as `odmpy` remain separate downstream tools.

The product must be distributable to people who do not know Python. Installation, first-run setup, diagnostics, privacy, and release packaging are part of the product definition from the first milestone.

## Phase 0 — foundation and distribution plumbing — built in v0.1 repository

- Python package and CLI shell
- domain models
- TOML configuration
- OS credential storage abstraction
- SQLite initialization/migration foundation
- provider isolation
- test/release CI
- PyInstaller standalone-binary build
- user-facing README and diagnostics

Acceptance: a tagged release can produce Python artifacts plus macOS ARM64, macOS Intel, Windows x64, and Linux x64 binaries in CI.

## Phase 1 — read-only Libby account + catalog — initial usable release

- guided official-site browser authentication, with passkey or setup-code recovery
- account synchronization
- linked card discovery
- Thunder library resolution
- search one or all linked libraries
- ebook/audiobook filtering
- live availability hydration
- Rich output and `--json`
- `doctor`

Acceptance workflow:

```text
libbyctl setup
libbyctl cards
libbyctl search "The Bee Sting" --author "Paul Murray"
libbyctl doctor
```

No circulation writes are exposed.

## Phase 2 — list ingestion and matching

- reading-list domain model
- CSV, text, ISBN import
- URL importer with explicit review
- title/author normalization
- ISBN matching
- fuzzy matching and confidence levels
- edition grouping

Acceptance: import the current Booker longlist and resolve every item to zero, one, or an explicitly ambiguous Libby work/edition group.

## Phase 3 — persistent planner

- current loan and hold state
- availability matrix across cards
- format preference
- card capacity/limits
- duplicate-hold avoidance
- transparent scoring
- persistent plans and refresh

Actions remain proposals only:

- BORROW
- HOLD
- KEEP_EXISTING_HOLD
- ALREADY_BORROWED
- SKIP
- NOT_OWNED
- NEEDS_REVIEW

Acceptance: `libbyctl plan booker-2026` creates a reproducible plan without making changes.

## Phase 4 — single-item circulation

Add private-provider methods behind a write boundary:

- borrow
- place hold
- cancel hold
- suspend/resume hold
- renew
- return

Requirements:

- explicit confirmation
- server-state preflight
- idempotency checks
- audit log without credentials
- no automatic action on ambiguous matches

## Phase 5 — plan apply and bulk operations

- refresh before apply
- show changed availability
- bulk hold/borrow execution
- bulk eligible returns
- per-action execution state
- safe restart after partial failure

Acceptance: re-running a partially completed plan never duplicates a successful hold/borrow.

## Phase 6 — external-library registry and scout

Maintain a separately sourced registry containing:

- library/system
- eligibility
- fee and term
- online/in-person requirement
- Libby eligibility
- official source URL
- verification date

`libbyctl scout <list>` compares a user's list to libraries they could potentially join.

## Phase 7 — library-card optimizer

Evaluate marginal value rather than raw collection size:

- titles newly covered
- titles immediately available
- materially improved waits
- desired-format coverage
- membership cost

The output explains tradeoffs rather than presenting opaque scores.

## Phase 8 — integration surfaces

Once CLI semantics are stable:

- local API
- MCP server
- Home Assistant hooks
- optional downstream trigger for `odmpy`

Write tools keep the same confirmation/idempotency boundary.

## Distribution roadmap

### v0.1 developer preview

- source package
- wheel/sdist
- macOS ARM64 binary through GitHub Actions
- other OS binaries built in the same matrix but marked preview

### v0.2 public read-only release

- Homebrew tap
- macOS ARM64/Intel
- Windows x64
- Linux x64
- PyPI / `uv tool install`
- clean-machine installation tests

### v0.3 circulation preview

- code signing/notarization work for macOS
- Windows signing path
- single-item writes

### v0.4 planner apply

- bulk circulation
- recovery/idempotency

### v0.5 scout

- membership registry and optimizer

## Public-release definition

A normal user should be able to install and get useful output without cloning source, installing dependencies manually, editing a config file, or copying a bearer token.

Target happy paths:

```text
brew install libbyctl/tap/libbyctl
libbyctl setup
```

and eventually:

```text
winget install libbyctl
libbyctl setup
```

A clean VM smoke test is mandatory before calling a release generally distributable.

## Architectural boundary

External services are replaceable providers:

```text
CatalogProvider
  -> ThunderCatalogProvider
  -> future OfficialOverDriveProvider

LibbyAccountProvider
  -> LibbyPrivateProvider
  -> future official provider if access becomes available
```

No application/planner code should contain endpoint URLs or private protocol payload details.

## Private endpoint assumptions isolated in adapters

The native account adapter uses the Libby web service pattern observed in current community clients:

- browser-assisted identity import after official-site recovery
- legacy experimental chip/bootstrap and setup-code clone methods
- sync account state

Direct CLI pairing has not passed a live test and is no longer the normal setup
path. The catalog adapter uses the current Thunder v2
library/media/availability surface. These are implementation details, not public
contracts, so contract tests and provider isolation are mandatory.

## Immediate next engineering work

1. Run normal `setup` from a packaged binary on a clean macOS machine with
   Chrome, then repeat on Windows and Linux; verify the browser driver and
   credential backend on each platform.
2. Observe natural token expiry or use a disposable account for revocation;
   verify reconnect keeps a good credential if interrupted.
3. Compare availability for the same title, format, edition, and card against
   the official Libby UI, and test multiple distinct cards.
4. Review the three unmatched 2026 Booker titles and representative matched
   editions in the official catalog; adjust scoring before planning relies on it.
5. Add bounded retry/backoff and a 15-minute availability cache after the
   provider behavior is validated. Prepare Homebrew distribution only after
   the clean-machine gate passes.
