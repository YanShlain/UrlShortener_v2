STATUS: READY

## What was built
v2 "Recent links" on the web page. `api.ts` gains `LinkItem` and `listLinks()` (GET /api/links, same error mapping as create, validates the response shape). New `RecentLinks.tsx` renders heading, privacy notice ("Recent links are visible to everyone."), and loading, error, empty and list states. Each row is an `<a href={short_url} target="_blank" rel="noopener noreferrer">` plus the full URL as a text node. `App.tsx` loads the list on mount and after each successful create (200 or 201). A few CSS rules wrap long URLs. No nginx, compose or proxy change.

## Async states and error handling
- `api.ts` listLinks: network error, non-2xx (server `detail`), invalid JSON or wrong shape all throw an Error.
- `App.tsx` loadList (about lines 20-35): `loading -> ok | error` in `ListState`; a request counter ref ignores stale responses (FM-20). List errors render only in the list area (`RecentLinks.tsx`), never in the form's alert.
- `App.tsx` onSubmit: unchanged `idle -> loading -> success | error`; success calls `loadList()`. Failed creates do not reload.
- The Recent links error text is shown with no `role="alert"`, so the form's alert stays separate.

## Decisions and trade-offs
- On reload after create, the old rows stay visible until the new response arrives (state stays `ok`, no flicker).
- The list error shows a fixed message, not the server's detail (FM-19).
- No retry button: the next create or page load recovers.
- `href` comes only from `short_url`; the full URL is text only. No `dangerouslySetInnerHTML`.

## Local check results
`npm run typecheck`, `npm test` (23 tests passed: 11 in App.test.tsx, 12 in RecentLinks.test.tsx) and `npm run build` all pass.
