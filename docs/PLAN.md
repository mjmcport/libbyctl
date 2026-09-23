# libbyctl implementation and distribution plan

Updated: 2026-09-23

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

- guided 8-digit setup-code authentication
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

## v0.1 endpoint assumptions isolated in adapters

The current account adapter uses the Libby web service pattern observed in current community clients:

- bootstrap identity chip
- clone with 8-digit setup code
- sync account state

The catalog adapter uses the current Thunder v2 library/media/availability surface. These are implementation details, not public contracts, so contract tests and provider isolation are mandatory.

## Immediate next engineering work

1. Test setup-code auth against a real account on macOS.
2. Capture sanitized fixture shapes for actual sync/card responses.
3. Validate library-key resolution for every linked card.
4. Validate search and wait-time fields against Libby UI.
5. Add cache with 15-minute availability TTL.
6. Add retry/backoff and token refresh-on-403.
7. Add GitHub repository URL and Homebrew tap automation.
8. Begin Phase 2 list/matching work only after the read-only foundation is verified.
