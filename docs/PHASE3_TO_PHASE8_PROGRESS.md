# Phase 3–8 implementation and test report

Date: 2026-09-23. Branch: `codex/libby-device-pairing`.

## Result

The Phase 3 read-only planner is operational for the connected one-card account.
It created and refreshed a 13-item Booker example plan using a temporary SQLite
database. The refresh kept the original snapshot and linked the new one. The
aggregate proposals were **3 NOT_OWNED, 1 HOLD, and 9 SKIP**, with no provider
warnings. There were no account writes. This reflects one catalog snapshot and
the card's current limits; proposals are not proof of patron-specific access.

The remaining phases are partially built. The circulation safety engine and
bulk restart logic passed simulated tests. A private Libby adapter now supports
explicit single-title borrow, hold, return, and hold cancellation. Research found
that a regular Libby device identity can make circulation requests through
Libby's private service; see `docs/PRIVATE_CIRCULATION_RESEARCH.md`.
The scout and optimizer work with reviewed registry
records, but no actual membership record is bundled because eligibility and fee
claims need location-specific official verification. The first integration
surface is read-only. No automatic circulation or download trigger is exposed.

## Implemented and verified

| Phase | Work | Evidence | Open gate |
| --- | --- | --- | --- |
| 3 | Saved plans, refresh history, loans/holds, availability by linked card, known limits, preferred formats, duplicate avoidance, explicit reasons | Synthetic capacity/error/duplicate tests and live 13-item create/refresh | Second distinct card, official UI edition/availability parity, clean-machine packaging |
| 4 | Provider-neutral engine, private Libby adapter, and CLI borrow/hold/return/cancel-hold; confirmation, preflight, hashed audit key | Mock request contracts and state transitions; live Pride and Prejudice ebook hold placed and canceled; borrow requests refused by account activity limit | Retry live borrow after the account limit clears; verify renew and hold suspension mapping before exposing those commands |
| 5 | Plan comparison before apply, per-action durable status, safe restart after a partial response failure | Simulated two-action batch: borrow succeeded, hold response lost, retry reconciled without a second write | Real provider state mapping and a controlled account test |
| 6 | Local registry import with eligibility text, fee/term, Libby/online flags, official HTTPS source, verification date; public-catalog scout | Validation, persistence, CLI import/list, synthetic catalog comparison | Verified regional records and official join conditions |
| 7 | Marginal coverage, immediate availability, shorter waits, preferred-format coverage, fee, and source age shown separately | Synthetic comparison and deterministic ordering | Real library examples and human review of cost/wait claims |
| 8 | Versioned aggregate `plans summary --json`; optional MCP stdio server exposing read-only local summaries and candidate records | CLI privacy test and in-process MCP client test with official SDK 2.2 | Stable CLI contract, authenticated local HTTP API, Home Assistant configuration, optional `odmpy` handoff |

The local suite, Ruff, and Pyright passed after these changes. The MCP test uses
the optional `mcp` extra; installations without that extra still run the main CLI.
The live check printed only aggregate action counts. Its temporary database was
removed on exit. No token, card ID, library key, or borrowed title was committed.

## Circulation access and remaining gate

OverDrive documents borrow/return through its
[Checkouts API](https://developer.overdrive.com/api-docs/circulation-apis/checkouts)
and hold actions through its
[Holds API](https://developer.overdrive.com/api-docs/circulation-apis/holds).
Those calls use an OAuth patron access token and approved API access;
[access requests](https://developer.overdrive.com/request-access) are tied to
partner-affiliated organizations. The current Libby browser identity is not an
approved OverDrive API credential. However, other projects use a regular Libby
identity for borrow/hold/return through Libby's separate private service. That
route does not require an OverDrive developer account. It is undocumented and
can change or reject a particular identity. This account was tested with a
temporary Pride and Prejudice ebook hold and cancellation; both succeeded.
The ebook and audiobook borrow attempts were refused with
`PatronExceededChurningLimit`, so successful live borrowing remains unverified.
The account was checked afterward: neither test loan nor temporary hold remained.
The audit ledger is local and stores only a hashed operation key, action, status,
and timestamp; it stores no credential, email, card ID, or title ID.

## Next test session

1. After the account's borrowing activity limit clears, retry one explicitly
   chosen Pride and Prejudice ebook borrow and one audiobook borrow, verify each
   in account state, then return both as requested. Test a non-JSON successful
   return response and reconcile any uncertain outcome with the same operation
   ID. Validate renewal and hold suspension fields before exposing their CLI
   commands. Keep the approved OverDrive API as a separate provider option.
2. Supply an eligibility area. Research candidate libraries against their
   official membership and Libby pages, record fee and verification date, then
   compare scout results with the official catalog/UI before recommending a card.
3. Re-run the Phase 1 clean-profile matrix on macOS ARM64/Intel, Windows, and
   Linux. Use a disposable profile for logout/revocation tests and a second
   distinct card for capacity/availability parity. Keep the PR in draft until
   these public-release gates pass.
4. After CLI/JSON semantics settle, add an authenticated loopback HTTP API,
   Home Assistant example, and opt-in `odmpy` handoff. Carry the same write
   confirmation and audit boundary into every integration surface.

## Reproduction

```bash
uv sync --extra dev --extra browser --extra mcp
uv run pytest -o addopts=''
uv run ruff check src tests
uv run pyright --pythonpath .venv/bin/python src
uv build

libbyctl lists import examples/booker-2026-longlist.csv --name 'Booker 2026'
libbyctl plan booker-2026
libbyctl plans list
libbyctl plans refresh PLAN_ID
libbyctl plans summary PLAN_ID --json
libbyctl libraries import REVIEWED_CANDIDATES.json
libbyctl scout booker-2026 --area YOUR_AREA
```

The example list is public, but saved plans and full `--json` outputs can contain
personal account data. Keep raw results local.
