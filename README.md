# libbyctl

`libbyctl` is a planner-first command-line interface for Libby/OverDrive. It is designed to answer a simple question across every library card you have:

> Where can I get this book, and what is the best path to it?

The project starts read-only: connect Libby, discover your cards, search all linked libraries, and compare live availability. Holds, borrowing, bulk returns, list planning, and nonresident-card scouting are phased in after the read-only foundation is validated.

> **Alpha / unofficial:** libbyctl is not affiliated with or endorsed by OverDrive or Libby. It uses interfaces also used by the Libby web application and community projects; those interfaces can change.

## Quick start

**Direct CLI pairing is currently blocked (2026-09-23).** Live device transfers fail
at `chip/clone` with HTTP 403 and `missing_chip`; the server also returns a notice
restricting its private API to the official Libby client. Automated pairing tests
use mocks and do not demonstrate working live sign-in. The setup commands below
are experimental; repeated pairing attempts are not a verified remedy. Use the
[official Libby website](https://libbyapp.com) or app to access your account.
The browser sign-in prototype below has now passed a real-account test: browser
restart, native account synchronization, fresh-process card listing, and catalog
search. Long-term credential renewal is still unverified.

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

### Browser sign-in prototype

Install Google Chrome, then from the project checkout:

```bash
uv sync --extra browser
uv run libbyctl auth browser --test-native
```

This opens the official Libby site in a separate Chrome profile under libbyctl's
data directory. Complete **Recover Your Data** with a passkey or the website's
setup code. The command waits for synchronized cards, restarts the browser to
verify persistence, then makes one native read-only synchronization request.
Only a native response matching the browser's cards permits saving a token in
the OS credential store. No token is printed. A failed test preserves existing
native credentials. Without `--test-native`, only browser sign-in is verified.

This is a diagnostic prototype, not yet a browser provider for `cards` or
`search`. Browser-only success does not establish native CLI access, and native
success does not establish long-term token renewal. The browser profile itself
contains sensitive session state; do not share it. `auth logout` currently
removes only the native token, not this browser profile. To clear browser login,
use Libby's reset option **inside this dedicated profile only**.

### Experimental direct pairing

Run:

```bash
libbyctl setup
```

`libbyctl setup` starts a new-device pairing and displays a short-lived code. On the Libby device that already has your cards, open **Menu → Copy To Another Device** and enter the current code shown by the CLI. Leave the command running while the code refreshes and the transfer completes. The resulting identity token is stored in the OS credential store rather than the config file or SQLite database.

Libby recommends recovery passkeys for its supported apps and browsers. The CLI currently uses Libby's setup-code recovery flow; it does not perform a passkey ceremony.

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

- guided Libby new-device pairing with rotating setup codes
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
