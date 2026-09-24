# Connected libraries and Booker audiobook test — 2026-09-23

## Account and discovery

The CLI's dedicated Libby browser was connected by signing into the two home
cards directly. A read-only native account sync verified both cards. The home
collections are **Minuteman Library Network** and **Up North Digital Collection**
(the latter contains the Glen Lake card). No card numbers, PINs, passkeys, or
account tokens are recorded here.

The public catalog record for each home collection exposes
`visitableLibraries`. The CLI now resolves those website IDs and preserves which
home card provides access. The live account resolved **22 distinct partners**:
15 through Up North and 7 through Minuteman. Together with the 2 home
collections, the read-only search scope is **24 collections**. The
`libbyctl libraries connected` command lists every collection and its access
route.

| Home collection | Partner collections |
| --- | --- |
| Up North Digital Collection | Bay County Library System; Download Destination; Genesee District Library; Great Lakes Digital Libraries; Jackson District Library; Lakeland Digital Library; Metro Net Library Consortium; Mideastern Michigan Library Cooperative; Midwest Collaborative for Library Services; Southwest Michigan Digital Library; St. Clair County Library System; Suburban Library Cooperative; Traverse Area District Library; White Pine Library Cooperative; Woodlands Downloadable Library |
| Minuteman Library Network | Boston Public Library; CLAMS; CW MARS; Merrimack Valley Library Consortium; NOBLE: North of Boston Library Exchange; Old Colony Library Network; SAILS Library Network |

## Booker 2026 audiobook scan

The bundled 13-title Booker longlist was imported as `booker-2026`. The CLI
searched all 24 catalogs for audiobooks with `--include-partners`. The scan
completed with **zero catalog search failures**. Nine titles had confident
audiobook matches; four had no confident match. The dated, machine-readable
snapshot is [booker-2026-audiobook-availability-2026-09-23.json](booker-2026-audiobook-availability-2026-09-23.json).

| Title | Result at scan time |
| --- | --- |
| The Shadow of the Object | No confident audiobook match |
| Switzy | Matched; shortest catalog wait estimate 98 days at Boston Public Library |
| Helen of Nowhere | No confident audiobook match |
| The End of Everything | Matched; shortest estimate 439 days at Download Destination |
| The Disappearers | Matched; shortest estimate 168 days at Merrimack Valley Library Consortium |
| Black Bag | Matched; shortest estimate 160 days at Boston Public Library |
| The Renovation | **Available now at Boston Public Library**; a second catalog read reported 100 available copies |
| May We Feed the King | Matched; shortest estimate 663 days at Download Destination |
| The Palm House | No confident audiobook match |
| The Things We Never Say | Matched; shortest estimate 147 days at St. Clair County Library System |
| John of John | Matched; shortest estimate 194 days at St. Clair County Library System |
| All Them Dogs | Matched; shortest estimate 193 days at Boston Public Library |
| The Vivisectors | No confident audiobook match |

These are public catalog results, not a promise that a visiting card can borrow
or place a hold on a particular title. Partner borrowing and hold rules differ.
No loan or hold was created during this scan.

## Two-card planner check

Using a temporary local database, the CLI created a read-only plan for the same
13 titles with both home cards. The proposals were **3 NOT_OWNED, 4 HOLD, and
6 SKIP**, with no provider warnings. Proposed entries selected both home cards.
The temporary plan and database were removed after the aggregate check. This
planner currently uses home collections only; it does not propose circulation
actions at partner libraries.

## Verification and remaining work

- The full local test suite, Ruff, and Pyright passed after partner discovery
  and search were added.
- A live single-title audiobook search across all 24 collections returned
  results without provider warnings. The full 13-title scan also completed
  without provider warnings.
- Passkey and setup-code transfers into the CLI browser returned to Welcome;
  the passkey attempt showed a 403 from Libby's `chip/clone` endpoint. Direct
  sign-in to the CLI browser succeeded and survived a browser restart.
- Partner catalog searches are read-only. Circulation commands currently
  require a card whose home key equals the target library key, so they cannot
  borrow from a partner collection. Before adding that capability, validate
  Libby's visiting-card rules and title-level eligibility in a live, controlled
  test. Do not infer borrowability from the public availability flag alone.

To repeat the read-only scan:

```bash
libbyctl libraries connected
libbyctl lists availability booker-2026 --format audiobook --include-partners --json
```
