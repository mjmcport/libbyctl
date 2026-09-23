# Authentication diagnosis and implementation plan

Research date: 2026-09-23. Repository reviewed: `07603a3827701540ce39d8572dd822da771577cb` on `codex/libby-device-pairing`.

## Recommendation

Build a browser-assisted authentication proof of concept before changing the private pairing protocol again. Complete recovery through Libby's official page in a dedicated, persistent browser profile, verify actual cards, and then make a controlled distinction between two possible providers:

1. A native HTTP provider, only if a user-authorized browser session demonstrably works outside the browser and survives identity refresh and process restart.
2. A browser provider that reads the user's authenticated Libby interface and returns normalized account/catalog data to the CLI while keeping credentials in the browser.

The second is the preferred fallback, not a proven implementation. Authentication through the official page does not by itself establish that a browser connector is supported by OverDrive. For a supported, distributable integration, pursue OverDrive's documented API credentials and QR authentication separately. None of these routes has been live-validated for this tool yet.

Do not advertise another pairing patch as a fix until it passes the acceptance gates below. This document is a plan; no authentication implementation, account access, or new live pairing was performed during this research turn.

## What the evidence actually establishes

| Observation | Supported conclusion | What it does not prove |
| --- | --- | --- |
| CLI obtains an identity and displays a code | Bootstrap and code creation can succeed | Identity is accepted for account transfer |
| Phone reports synchronization; polling returns a grant | User approved the transfer and the handshake advanced | Target successfully applied the grant |
| `chip/clone` returns 403 and `missing_chip` | That request was refused | Exact internal cause, permanent ban, or impossibility of every integration |
| Response includes a private-API restriction notice | The server states a real restriction | The notice uniquely identifies this particular authentication fault |
| Two empty test sessions reproduced the error in prior work | The same response can occur without this user's account | An empty source is a valid substitute for a card-bearing source; both failures have identical causes |
| Twelve automated tests passed previously | The modeled local behaviors pass | Compatibility with live Libby |

Earlier conclusions that the notice conclusively ruled out authentication were too strong. The official web client itself handles `missing_chip` by reacquiring an identity and retrying once. That is evidence the result can be recoverable, not a guarantee our failure is recoverable. Its generic recovery code does not reveal the server's actual decision. [Official web-client source](https://libbyapp.com/dewey-22.1.1/src/main.js)

## Concrete findings in our code

### 1. The new notice check changes control flow prematurely

`src/libbyctl/providers/libby/client.py:96` recognizes text in a 403 notice and raises before the existing `missing_chip` recovery at line 103. Our newest message consequently reports a policy conclusion instead of retaining endpoint/result details and identifying the failed authentication stage. A notice should be recorded as a separate diagnostic fact; it is not a substitute for a verified error taxonomy. Do not silently ignore it either.

### 2. Post-transfer identity handling differs from the reference

At lines 213–214, we clear `self.token` and call unauthenticated `_reacquire_chip()` with `r=<chip>`. The official client's `forgetIdentity()` clears the in-memory field, but `acquireChip()` first looks up the persisted identity. It ordinarily refreshes using that identity and the chip prefix. Our implementation mistook clearing one field for discarding the saved credential. This is a concrete mismatch, but it occurs after clone and cannot alone explain the earlier clone failure. [Official web-client source](https://libbyapp.com/dewey-22.1.1/src/main.js)

### 3. Session persistence is incomplete

`CredentialStore` saves only the token. `_load_account()` constructs a new client with `chip_id=None`. Therefore recovery cannot refresh an identity after process restart even when it could do so in the original setup process. Refreshed tokens during normal commands also have no persistence callback. A successful one-time setup would not demonstrate durable authentication. Store a versioned session record atomically, or deliberately keep the entire session in a persistent browser provider.

### 4. Bootstrap/refresh requests differ from a current community client

The reviewed KOReader client adds an identity-dependent header on chip creation/refresh, refreshes once on `missing_chip`, retains credentials for post-clone refresh, and requires nonempty synchronized cards before reporting success. Our client does not implement all of those behaviors. Prior tests of a bootstrap-header variation still failed with empty sources; the header is a candidate difference, not a demonstrated cure. The project reports setup-code authentication, but I did not execute it or independently verify its live success. [Pinned source](https://github.com/jadehawk/libby-dashboard.koplugin/blob/4b90996bad10f7b86461e74a56b6ddd9f6f29c86/libby-dashboard.koplugin/libby_client.lua), [project description](https://github.com/jadehawk/libby-dashboard.koplugin)

Another current project's authentication module links a library card and uses a different, older code role before reminting its identity. This is supporting evidence that identity lifecycle matters, not a drop-in replacement for our phone-approved flow. Do not execute its unrelated download functionality. [Pinned authentication source](https://github.com/JavaGT/libby-archiver/blob/6c8029701bac2ea120faff9623a4782ada4cbb75/src/auth.mjs)

### 5. Passing tests encode several assumptions

The pairing mock returns successful clone and synchronization responses we have not observed with a real account. It also explicitly expects the questionable unauthenticated post-clone reacquisition. The newer notice test proves early termination, not that early termination is the correct recovery policy. Revise these tests around observed behavior and independent state-transition invariants rather than simply reproducing the implementation.

## Authentication options

| Route | What it offers | Main limitation | Recommendation |
| --- | --- | --- | --- |
| Official-page login plus browser provider | Uses normal passkey/code login; avoids reimplementing initial device transfer | Requires browser integration and resilient data extraction; not an official integration contract | First practical proof of concept |
| User-authorized browser session imported into native provider | Potentially retains lightweight HTTP CLI after browser login | Portability, expiry, and refresh are unverified; private API dependency remains | One bounded diagnostic, then decide |
| Repair direct CLI pairing | Smallest apparent architectural change | Multiple lifecycle mismatches; no successful control; private API changes | Secondary investigation after establishing a working session |
| Approved OverDrive QR authentication | Documented delegated login and token renewal | Application approval and library/partner access; different APIs | Supported long-term route |
| Direct library-card/PIN login | Documented patron authentication with approved credentials | Handles sensitive credentials and is library-specific | Secondary to official QR |
| Library list or exported-data import | Keeps some planning useful without account login | Does not deliver live authenticated account access | Degraded mode only |

Libby officially supports recovery passkeys and setup codes through its own recovery UI. A passkey is useful for the browser connection; it is not a string we should ask users to paste into the CLI. [Libby recovery instructions](https://help.libbyapp.com/en-us/6070.htm)

OverDrive's QR flow uses an approved client key and collection website ID, sends the user through its login page, and returns an authorization code to a callback. Token exchange requires the client secret. Access tokens last one hour; refresh is documented for up to 30 days with rotating refresh tokens. These are OAuth credentials for the public OverDrive APIs, not replacements for a Sentry identity. The reviewed documentation does not specify a public-client/PKCE or localhost callback contract; confirm those before designing a standalone CLI release. [QR authentication](https://developer.overdrive.com/api-docs/authentication/qr-code-authentication)

API access is not anonymous self-service: the request page limits eligibility to organizations affiliated with partner libraries or schools. Circulation production access also requires implementation review, with library-specific credential arrangements. Do not assume the developer can access every user's libraries with one key. [Access eligibility](https://developer.overdrive.com/request-access), [application process](https://developer.overdrive.com/getting-started/application-process)

The public Patron Information API exposes patron-specific collection links, limits, and links to loans/holds. Its collection token should be obtained each session and used for eligible catalog availability. The reviewed docs do not establish an API for enumerating all cards linked to a Libby installation or exporting Libby tags. Model separate library connections until confirmed otherwise. Migrating only login while leaving our Thunder/Sentry data calls unchanged would not complete a public-API integration. [Patron Information API](https://developer.overdrive.com/api-docs/circulation-apis/patron-information)

## Implementation sequence and decision gates

### Phase 1 — Establish a real authenticated control

Build an opt-in local diagnostic runner with redaction enabled before collecting any account traffic. Open the official Libby website in a dedicated visible browser profile. The user completes passkey recovery or code approval in the official UI; do not reset their existing phone/browser data. Confirm cards actually appear and survive a page reload. This is the first necessary user-assisted checkpoint, after the runner is ready, not another speculative CLI setup attempt.

Record only stage, HTTP status, sanitized result, notice category, token presence/change booleans, same-device boolean, expiry when available, and card count. Do not save raw headers, authorization codes, grants, tokens, card numbers, PINs, or unredacted HAR files. Compare shape and lifecycle, not secret values.

If official login fails too, investigate that account/browser recovery failure first. If it succeeds, it provides the missing positive control.

### Phase 2 — Test session portability once

With the user's explicit selection of that tool-owned session, keep credentials in process memory and perform one read-only native account synchronization. Never ask for a token in chat or put one on the command line. Validate returned account data before saving any credential; preserve an existing valid session if import fails.

| Browser result | Native result | Next action |
| --- | --- | --- |
| Works | Synchronizes expected cards | Test supported identity refresh and a fresh CLI process; consider native provider |
| Works | 401/403 | Stop portability attempts; prototype browser provider |
| Works | Empty/different account | Reject connection; investigate identity mismatch |
| Fails | Not attempted | Resolve official login; no CLI compatibility claim |

If native portability works, replace `_reacquire_chip` assumptions with verified lifecycle handling, persist the device identity and token together, and save every successful rotation. Decoded JWT fields may be diagnostic hints, never proof of authenticity; the server response is the authority. Test current token formats rather than assuming the older payload layout is stable.

### Phase 3 — Browser provider if needed

Proposed `libbyctl auth browser` launches the dedicated profile and waits for the official page to show an authenticated account. `cards`, `search`, and later read-only loans/holds use a provider interface independent of Sentry. Begin with the rendered account/library UI and user-visible catalog results; do not make private globals or replayed endpoints the architectural foundation. Define explicit pagination, freshness, and per-library completeness checks. A browser connector that reads only the first visible page is not sufficient.

A visible persistent browser context is suitable for the first local prototype; do not automate the user's default Chrome profile. Browser library support for persistence does not guarantee Libby/passkey compatibility, which must be tested on the actual Mac. [Playwright persistent contexts](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context)

For a packaged connector, evaluate an extension plus native messaging. The extension service worker mediates messages from the selected Libby tab to an allowlisted local host. Validate sender origin, message schema, and request identity; return normalized data rather than credentials. Native messaging supports this transport but does not supply Libby data extraction. Decide on an extension only after the small browser proof of concept meets completeness tests. [Chrome native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)

### Phase 4 — Supported API track

Prepare an access inquiry describing a read-only, multi-library discovery/planning tool. Ask about partner eligibility, QR scopes, callback restrictions, public native clients, confidential-client secret storage, multiple libraries, and required production-review functionality. Do not send the inquiry without user authorization.

If approved, implement a separate OverDrive provider: QR login, server-side code exchange where a confidential secret is required, secure rotating token storage, per-library account records, and the documented Discovery/Circulation endpoints. Never ship a shared client secret in an open-source CLI binary. A local private installation with user-supplied approved credentials is a different deployment case. Test against the supplied integration environment before production. [Integration environment](https://developer.overdrive.com/getting-started/integration-library)

## Acceptance criteria before calling authentication fixed

- Official login establishes an account with the user's expected cards.
- The chosen provider returns the same library/card count and representative loan/hold counts.
- A new CLI process can reuse the connection without phone approval.
- Native identity/token renewal or browser session renewal is demonstrated, not only mocked.
- An expired/revoked session produces a reconnect instruction without loops or overwriting a good credential.
- Search and availability work across at least two connected libraries where available; missing libraries are explicit.
- Secrets are absent from shell history, diagnostic output, fixtures, screenshots, and repository changes.
- Logout removes the tool's local session without resetting the phone's Libby data.
- Package installation and browser dependency setup work outside the development checkout.
- Tests distinguish mocked unit coverage, local integration coverage, and an opt-in successful real-account smoke test.

## Research provenance and limits

Reviewed local application, credential store, account mapping, catalog provider, and pairing tests. Re-inspected the public official web bundle previously fetched this session: SHA-256 `9713490737091fe373c4bc25f922895b77169dafcdceefdc026b01c28107e774`. Its URL is versioned but the hash is the reproducibility reference. Community source revisions are pinned above; no third-party code was executed. Live failures described here are from earlier work in this task, not newly run experiments. No user credentials were inspected during this research. Application code and the draft PR were not changed as part of this plan.
