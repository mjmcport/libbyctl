# libbyctl

`libbyctl` helps you search the catalogs connected to your Libby account and
compare ebook and audiobook availability. It can import reading lists and flag
catalog matches for review. Borrowing, holds, returns, and bulk actions are not
available yet.

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

The bundled 2026 Booker longlist example is transcribed from the
[official Booker announcement](https://thebookerprizes.com/media-centre/press-releases/longlist-for-booker-prize-2026-rewards-risk).

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
