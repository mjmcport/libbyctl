# Provider protocol notes

These notes exist so the implementation can be maintained without leaking service-specific assumptions into domain/planner code.

## Libby account adapter

Current community implementations and observed web-client behavior use `https://sentry.libbyapp.com` for account/device state.

Read-only v0.1 flow:

1. `POST /chip?client=dewey` to obtain a fresh identity.
2. `POST /chip/clone/code` with the 8-digit setup code while authenticated with that identity.
3. `GET /chip/sync` to retrieve synchronized cards, loans, and holds.

The service is private/undocumented and can change. Keep all details in `providers/libby`.

## Thunder catalog adapter

Base: `https://thunder.api.overdrive.com/v2`

Current read operations used by v0.1:

- `GET /libraries/?websiteIds=...&x-client-id=dewey`
- `GET /libraries/{libraryKey}/media/?query=...&x-client-id=dewey`
- `GET /libraries/{libraryKey}/media/{titleId}/availability?x-client-id=dewey`

Future bulk availability can use the provider's bulk availability route.

## Clean implementation note

The project does not vendor or copy source from existing GPL clients. Public implementations are used as protocol references and compatibility checks; libbyctl code is written independently behind its own interfaces.
