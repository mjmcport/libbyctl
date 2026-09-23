# libbyctl

`libbyctl` helps you search the catalogs connected to your Libby account and
compare ebook and audiobook availability. It can import reading lists, make
read-only loan/hold plans, and compare sourced candidate libraries. Explicit
single-title borrow, hold, return, and hold management are available through
the connected Libby account. Bulk account changes are not exposed yet.

This is an unofficial alpha. It uses interfaces that can change, and it is not
affiliated with OverDrive or Libby.

## Install and connect

For a source installation, install the browser extra:

```bash
uv tool install 'libbyctl[browser]'
libbyctl setup
libbyctl cards
libbyctl search 'The Hobbit' --format ebook
libbyctl doctor
```

The standalone release binary includes the browser runtime. Install Google
Chrome before running `libbyctl setup`. Setup opens the official Libby site in
a dedicated Chrome profile. Complete **Recover Your Data** there with a passkey
or setup code. The tool verifies that cards persist after restarting the browser,
then verifies the same cards through a read-only account request. Only then does
it save the native identity in the OS credential store. If verification fails,
the existing native credential is retained.

`libbyctl auth status` checks the saved identity. If it expires or is revoked,
run `libbyctl setup` again. A native session with a saved device chip can attempt
one refresh; a browser-derived token currently relies on browser reconnection.
Long-term renewal has not been proven with a naturally expired account. The
dedicated browser profile contains sensitive session state. `libbyctl auth logout`
removes both that profile and the native identity from this computer; it does not
reset another Libby device.

Advanced users can import an existing token with `libbyctl auth token`, or use
`LIBBYCTL_TOKEN` for one process. A bare token has no device chip for refresh.

## Search

```bash
libbyctl search 'The Hobbit' --author Tolkien
libbyctl search 'The Hobbit' --format audiobook --library my-library-key
libbyctl search 'The Hobbit' --json
```

`--format` accepts `ebook` or `audiobook`; unknown library keys are rejected with
the available choices. JSON search output is an object with `results` and
`warnings` arrays. A library search failure keeps results from other libraries
and is reported in `warnings`; unavailable availability metadata is also marked
as a warning and the affected result has `availability: null`. If every selected
library fails, the command exits with status 2. `doctor` exits with status 2
when a required check fails.

## Reading lists (Phase 2 preview)

```bash
libbyctl lists import examples/booker-2026-longlist.csv --name 'Booker 2026'
libbyctl lists show booker-2026
libbyctl lists match booker-2026 --json
```

CSV files need `title` and/or `isbn` headers; `author` is optional. Text files
accept one title per line, optionally followed by an em dash and author. `.isbn`
files accept one ISBN per line and validate its check digit. URL import currently
accepts direct HTTPS `.csv`, `.txt`, or `.isbn` files. It previews all items
and prints a SHA-256 fingerprint; repeat with that fingerprint to save the same
content after review:

```bash
libbyctl lists import-url 'https://example.org/books.csv' --name 'My list'
libbyctl lists import-url 'https://example.org/books.csv' --name 'My list' --confirm SHA256_FROM_PREVIEW
```

Matching groups equivalent title/author editions across libraries. Each item is
reported as `matched`, `ambiguous`, `unmatched`, or `incomplete` if a library
search failed. Scores are suggestions for review, not evidence that two catalog
records are the same work. Import and match make no circulation changes.

To check one format for the saved list, use:

```bash
libbyctl lists availability booker-2026 --format audiobook
libbyctl lists availability booker-2026 --format audiobook --json
```

This checks the catalog collections associated with cards on the **CLI's
connected Libby identity**. Connect the CLI through **Recover Your Data** from
the Libby app that has your saved cards; adding one card to a fresh browser
identity does not copy the others. If the CLI is already connected to the wrong
identity, run `libbyctl auth logout` and then `libbyctl setup`, selecting
**Recover Your Data** in the new browser window. This removes only the CLI's
saved identity and dedicated browser profile; it leaves the main Libby app and
local reading lists intact. The command reports public catalog
availability, not a guarantee that a particular card can borrow. Partner
collections without a saved card are not searched yet.

The bundled 2026 Booker longlist example is transcribed from the
[official Booker announcement](https://thebookerprizes.com/media-centre/press-releases/longlist-for-booker-prize-2026-rewards-risk).

## Read-only plans

```bash
libbyctl plan booker-2026
libbyctl plans list
libbyctl plans show PLAN_ID --json
libbyctl plans refresh PLAN_ID
```

Plans compare the current loans and holds, catalog matches, availability, format
preferences, and known card limits. They propose `BORROW`, `HOLD`,
`KEEP_EXISTING_HOLD`, `ALREADY_BORROWED`, `SKIP`, `NOT_OWNED`, or `NEEDS_REVIEW`.
The proposal reserves capacity for earlier entries but never changes the library
account. Weak or ambiguous matches, unknown ownership, and incomplete searches need
review. A refreshed plan is saved as a new snapshot; the old one remains intact.

## Single-title circulation (preview)

Find an exact edition ID, then use a stable operation ID for each intended
change. The command shows the book and card for confirmation; `--yes` is for an
action you have already reviewed.

```bash
libbyctl circulation candidates 'Pride and Prejudice' --format ebook --author 'Jane Austen'
libbyctl circulation borrow TITLE_ID --format ebook --operation-id my-borrow-1
libbyctl circulation return TITLE_ID --operation-id my-return-1
libbyctl circulation hold TITLE_ID --format ebook --operation-id my-hold-1
libbyctl circulation suspend-hold TITLE_ID --days 7 --operation-id my-suspend-1
libbyctl circulation resume-hold TITLE_ID --operation-id my-resume-1
libbyctl circulation cancel-hold TITLE_ID --operation-id my-cancel-1
```

Each command reads fresh account and catalog state before a write and verifies
the account state afterward. If a response is uncertain, retry with the same
operation ID so the tool can reconcile the result without repeating the write.
Use a new operation ID only for a distinct action after resolving a structured
rejection. The private Libby service is undocumented; library account rules can
refuse an otherwise available title. In the September 2026 live test, borrow
requests were refused with `PatronExceededChurningLimit`, while a temporary hold
was placed, suspended, resumed, and canceled successfully. No test loan or hold
remained afterward.

## Review recent borrowing activity

Libby's [Timeline](https://help.libbyapp.com/en-us/categories/reading-history.htm)
shows borrowing and returns from all linked libraries. In Libby, open **Shelf →
Timeline → Actions → Export Timeline → Spreadsheet** and save an **unfiltered**
export. Then run:

```bash
libbyctl circulation activity PATH_TO_EXPORTED_CSV
libbyctl circulation activity PATH_TO_EXPORTED_CSV --days 14 --json
```

The command reads the CSV locally, counts recent borrowed and returned events
by library, and shows the ten most recent events. It does not store or upload the
export. Libby's export identifies the library, not the individual card, so
multiple cards at one library cannot be separated. Filters applied before export
can hide activity; [recover card history](https://help.libbyapp.com/en-us/6281.htm)
in Libby if older activity is missing. Returns do not cancel checkout events in
this report. The count is useful context for a `PatronExceededChurningLimit`
rejection, but OverDrive has not published a reliable threshold or scope for that
restriction, so the tool does not claim that another borrow will succeed.

## Candidate libraries

`libbyctl libraries import FILE.json` accepts an array of reviewed records with
`name`, `library_key`, `eligibility_area`, `eligibility_rule`, `membership_fee_usd`,
`term_months`, `online_join`, `libby_access`, `official_source_url` (HTTPS), and
`verified_on` (ISO date). No candidate records ship with the app; verify the
official eligibility and fee source before importing one.

```bash
libbyctl libraries import my-candidates.json
libbyctl libraries list
libbyctl scout booker-2026 --area Michigan
libbyctl scout booker-2026 --plan-id PLAN_ID --json
```

`scout` compares public catalog coverage with the latest saved plan for the
list. It shows newly covered titles, immediate availability, shorter estimated
waits, preferred-format coverage, fee, source age, and eligibility text. These
are research leads: a matching area does not establish membership eligibility
or personalized borrowing access.

The circulation engine keeps an audit record without credentials or title/card
IDs. Renewal has a private-client method but is not exposed as a CLI command
until its account-state checks are verified. See
[`docs/PHASE3_TO_PHASE8_PROGRESS.md`](docs/PHASE3_TO_PHASE8_PROGRESS.md).

## Local integrations

`libbyctl plans summary PLAN_ID --json` returns only aggregate action counts,
without title or card IDs. A Home Assistant command-line sensor or another
local program can consume this versioned JSON output. Install `libbyctl[mcp]`
to expose the same saved summaries, saved plan names, and sourced candidate
libraries through `libbyctl mcp` over a local stdio connection. The MCP server
has no write tools and does not contact the live account. An HTTP API and an
automatic `odmpy` trigger remain future work.

## Development and packaging

```bash
uv sync --extra dev --extra browser
uv run pytest
uv run ruff check src tests
uv run pyright --pythonpath .venv/bin/python src
uv run pyinstaller packaging/pyinstaller/libbyctl.spec --noconfirm
./dist/libbyctl version
```

The release workflow builds Python artifacts and macOS ARM64/Intel, Windows x64,
and Linux x64 preview binaries. A clean-machine first-run test on each platform
is still required before calling the release generally distributable. See
[`docs/PLAN.md`](docs/PLAN.md) and [`docs/PHASE1_TEST_REPORT.md`](docs/PHASE1_TEST_REPORT.md).

Identity tokens are not written to configuration or SQLite. Card JSON and
reading lists may be personal; avoid sharing their output or local data files.

## License

MIT.
