# Provider protocol notes

These notes exist so the implementation can be maintained without leaking service-specific assumptions into domain/planner code.

## Libby account adapter

Direct anonymous device transfer remained blocked during the Phase 1 check:
`POST /chip/clone` returned HTTP 403 with `result=missing_chip`, and the server
returned a notice restricting this private API to the official Libby client.
The later official-site browser setup and native account cross-check succeeded
for one linked card, so read-only sync now works with an imported Libby identity.
That does not establish whether private circulation writes will work. Mock tests
cannot validate service acceptance, and the cause of every `missing_chip` response
is still unknown.

Current community implementations and observed web-client behavior use `https://sentry.libbyapp.com` for account/device state.

The attempted direct recovery-code flow treats the CLI as the new device. It:

1. `POST /chip?c=d:22.1.1&s=0` to obtain a fresh chip and identity.
2. `GET /chip/clone/code?code=&role=pointer` to create a short-lived setup code, then polls `GET /chip/clone/code?code=...&role=pointer` while the user enters the code on the original device using **Menu → Copy To Another Device**.
3. When the poll returns `result=fulfilled`, `POST /chip/clone` with the returned blessing.
4. `POST /chip?c=d:22.1.1&s=0&v=<chip-prefix>` with the temporary identity to refresh the paired chip identity.
5. `GET /chip/sync` to retrieve synchronized cards, loans, and holds.

Codes expire after about one minute; the CLI requests and displays a replacement while waiting. Libby recommends recovery passkeys in supported clients, but this CLI uses the documented setup-code fallback and does not implement WebAuthn/passkey recovery.

The account endpoints are private/undocumented and can change. This sequence follows the Libby web client's recovery-code behavior observed on 2026-09-23; direct CLI pairing did not succeed in that check. Normal setup now uses the official-site browser flow. Keep protocol details in `providers/libby` and recheck the web client if pairing changes. See `docs/PRIVATE_CIRCULATION_RESEARCH.md` for the separate write-path research.

## Thunder catalog adapter

Base: `https://thunder.api.overdrive.com/v2`

Current read operations used by v0.1:

- `GET /libraries/?websiteIds=...&x-client-id=dewey`
- `GET /libraries/{libraryKey}/media/?query=...&x-client-id=dewey`
- `GET /libraries/{libraryKey}/media/{titleId}/availability?x-client-id=dewey`

Future bulk availability can use the provider's bulk availability route.

## Clean implementation note

The project does not vendor or copy source from existing GPL clients. Public implementations are used as protocol references and compatibility checks; libbyctl code is written independently behind its own interfaces.
