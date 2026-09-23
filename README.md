# libbyctl

`libbyctl` is a planner-first command-line interface for Libby/OverDrive. It is designed to answer a simple question across every library card you have:

> Where can I get this book, and what is the best path to it?

The project starts read-only: connect Libby, discover your cards, search all linked libraries, and compare live availability. Holds, borrowing, bulk returns, list planning, and nonresident-card scouting are phased in after the read-only foundation is validated.

> **Alpha / unofficial:** libbyctl is not affiliated with or endorsed by OverDrive or Libby. It uses interfaces also used by the Libby web application and community projects; those interfaces can change.

## Quick start

### macOS — current developer build

```bash
uv tool install .
libbyctl setup
libbyctl cards
libbyctl search "The Bee Sting" --author "Paul Murray"
```

For the first public release the intended installation becomes:

```bash
brew install libbyctl/tap/libbyctl
libbyctl setup
```

GitHub Releases are configured to build standalone macOS ARM64/Intel, Windows x64, and Linux x64 binaries when a version tag is pushed.

## Connect Libby

Run:

```bash
libbyctl setup
```

In Libby, use **Settings → Copy To Another Device**, reveal the 8-digit setup code, and enter it when prompted. The resulting identity token is stored in the OS credential store rather than the config file or SQLite database.

Advanced/recovery users can provide an existing token:

```bash
libbyctl auth token
libbyctl auth status
```

or set `LIBBYCTL_TOKEN` for a temporary process environment.

## Search all linked libraries

```bash
libbyctl search "Project Hail Mary"
libbyctl search "The Bee Sting" --author "Paul Murray"
libbyctl search "Orbital" --format audiobook
libbyctl search "Orbital" --json
```

## Diagnose setup

```bash
libbyctl doctor
```

## Current v0.1 scope

Implemented:

- guided Libby setup-code login
- secure credential abstraction
- account/card sync
- linked-library resolution
- Thunder catalog search
- per-title availability checks
- multi-library concurrent search
- Rich terminal tables
- JSON output
- local SQLite initialization
- `doctor`
- test suite
- PyInstaller specification
- GitHub Actions test/release workflows

Deliberately not enabled yet:

- borrow
- place/cancel/suspend holds
- return/renew
- bulk circulation
- reading-list planner
- paid/nonresident-card scout

Those are the next phases described in [`docs/PLAN.md`](docs/PLAN.md).

## Development

```bash
git clone <your-repository-url>
cd libbyctl
uv sync --extra dev
uv run pytest
uv run libbyctl --help
```

## Build a standalone binary

```bash
uv sync --extra dev
uv run pyinstaller packaging/pyinstaller/libbyctl.spec --noconfirm
./dist/libbyctl version
```

PyInstaller builds for the platform it is running on; the GitHub Actions release matrix handles each operating system separately.

## Safety and privacy

- Libby identity tokens are never written to `config.toml` or the local SQLite database.
- Card display values are masked in normal terminal output.
- JSON output can contain account metadata; treat it as private.
- Write/circulation operations are intentionally absent from v0.1.

## License

MIT. This repository is an independent clean implementation informed by publicly observable service behavior and public community documentation; it does not copy source from the GPL Calibre plugin.
