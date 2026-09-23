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
bulk restart logic passed simulated tests, but no approved live circulation
provider is configured. The scout and optimizer work with reviewed registry
records, but no actual membership record is bundled because eligibility and fee
claims need location-specific official verification. The first integration
surface is read-only. No automatic circulation or download trigger is exposed.

## Implemented and verified

| Phase | Work | Evidence | Open gate |
| --- | --- | --- | --- |
| 3 | Saved plans, refresh history, loans/holds, availability by linked card, known limits, preferred formats, duplicate avoidance, explicit reasons | Synthetic capacity/error/duplicate tests and live 13-item create/refresh | Second distinct card, official UI edition/availability parity, clean-machine packaging |
| 4 | Provider-neutral single-item engine for borrow, hold, cancel/suspend/resume hold, renew, return; confirmation, preflight, hashed audit key | Simulated success, unknown-capacity rejection, lost-response reconciliation, absence checks | Approved circulation credentials/provider; live calls not attempted |
| 5 | Plan comparison before apply, per-action durable status, safe restart after a partial response failure | Simulated two-action batch: borrow succeeded, hold response lost, retry reconciled without a second write | Real provider state mapping and disposable integration account |
| 6 | Local registry import with eligibility text, fee/term, Libby/online flags, official HTTPS source, verification date; public-catalog scout | Validation, persistence, CLI import/list, synthetic catalog comparison | Verified regional records and official join conditions |
| 7 | Marginal coverage, immediate availability, shorter waits, preferred-format coverage, fee, and source age shown separately | Synthetic comparison and deterministic ordering | Real library examples and human review of cost/wait claims |
| 8 | Versioned aggregate `plans summary --json`; optional MCP stdio server exposing read-only local summaries and candidate records | CLI privacy test and in-process MCP client test with official SDK 2.2 | Stable CLI contract, authenticated local HTTP API, Home Assistant configuration, optional `odmpy` handoff |

The local suite, Ruff, and Pyright passed after these changes. The MCP test uses
the optional `mcp` extra; installations without that extra still run the main CLI.
The live check printed only aggregate action counts. Its temporary database was
removed on exit. No token, card ID, library key, or borrowed title was committed.

## Why circulation is gated

OverDrive documents borrow/return through its
[Checkouts API](https://developer.overdrive.com/api-docs/circulation-apis/checkouts)
and hold actions through its
[Holds API](https://developer.overdrive.com/api-docs/circulation-apis/holds).
Those calls use an OAuth patron access token and approved API access;
[access requests](https://developer.overdrive.com/request-access) are tied to
partner-affiliated organizations. The current Libby browser identity is not an
approved OverDrive API credential. The official examples also do not establish
how to map this project's Libby card IDs to an authorized patron API identity.
For that reason the new engine has no production write adapter or live write CLI.
The audit ledger is local and stores only a hashed operation key, action, status,
and timestamp; it stores no credential, email, card ID, or title ID.

## Next test session

1. Use a disposable authorized OverDrive integration account and approved API
   access to implement/test the official adapter. Verify exact card and title
   mapping, borrow/hold/return behavior, and renew support from approved docs.
   Exercise an ambiguous match, capacity change, response loss, and partial
   batch restart. Do not use the ordinary connected Libby account for trial writes.
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
