# Private Libby circulation research

Date: 2026-09-23

## Finding

An OverDrive developer integration account is required for the documented
Circulation API, but it is not technically required for a client acting through
Libby's separate private service. Open-source clients use a regular Libby device
identity linked to library cards to borrow titles and place holds. This corrects
the earlier Phase 3–8 report, which treated approved API credentials as the only
practical path to live circulation.

## Direct evidence

- The [OverDrive Libby calibre plugin](https://github.com/ping/libby-calibre-plugin)
  documents setup using a regular eight-digit Libby setup code. Its Search view
  offers Borrow and Hold actions with a selected linked card. Its
  [client source](https://github.com/ping/libby-calibre-plugin/blob/main/calibre-plugin/libby/client.py)
  sends bearer-authenticated requests to Libby's private service: POST to
  `card/{card_id}/loan/{title_id}` for borrowing, POST to
  `card/{card_id}/hold/{title_id}` for a hold, and corresponding DELETE/PUT calls
  for return, cancel, renew, and hold management. This project is GPL-3.0; use it
  as a protocol reference and implement our adapter independently.
- [odmpy](https://github.com/ping/odmpy) exposes `libbyreturn` and `libbyrenew`
  CLI actions; its [Libby client](https://github.com/ping/odmpy/blob/master/odmpy/libby.py)
  also includes borrowing and hold methods. Its CLI does not currently expose a
  general search-and-borrow command. It is supporting protocol evidence, not a
  complete CLI substitute.
- The more recent [KOReader Libby dashboard](https://github.com/jadehawk/libby-dashboard.koplugin)
  documents borrowing available holds through a regular Libby setup-code flow.
  Its [client source](https://github.com/jadehawk/libby-dashboard.koplugin/blob/main/libby-dashboard.koplugin/libby_client.lua)
  posts to the same loan path on `sentry.libbyapp.com` with a Libby identity token
  and handles a `missing_chip` response. Its demonstrated scope is borrowing
  ready holds; the older calibre plugin has the broader search-and-borrow flow.
- [OverDrive's access process](https://developer.overdrive.com/getting-started/application-process)
  applies to its supported developer APIs. It does not make the private Libby
  route an official or stable integration.

## Implication for libbyctl

The connected account already has a working Libby identity for read-only sync.
The existing `LibbyClient` uses `sentry.libbyapp.com`, and the Phase 4/5 engine
already requires explicit confirmation, fresh state, and retry reconciliation.
The next implementation step is a private-service circulation adapter that uses
those boundaries. Borrowing must include a title format and supported loan
period; placement and management of holds require card/title state mapping.
Before exposing writes, test the protocol with mock transport and verify one
chosen action against the official Libby interface. A successful read-only sync
does not establish that a write will work for this identity or card. Private
endpoints can change or return a restriction/error, so keep the adapter isolated
and report such errors without silently repeating a write.

An official Circulation API provider remains a future option for organizations
that obtain credentials. Browser interaction with the normal Libby site is
another possible fallback if the private endpoint proves unreliable, but it has
not been implemented or tested here.
