Plan change (user approved items 1–5 below: "Yes, send 1–5"):

1. Parse the URL instead of matching text. Use `urllib.parse` and compare the scheme without regard to case, so `JavaScript:` or ` javascript:` with a leading space can't get through a prefix check.
2. Require a real host. Reject `http://`, `http:///path`, and any control characters or whitespace inside the URL.
3. Reject user:password parts. A link like `http://good.com@evil.com` actually goes to `evil.com`, a common phishing trick.
4. Light, safe normalization before the duplicate check:
   - make the scheme and host lowercase
   - drop the default port (`:80` for http, `:443` for https)
   - turn an empty path into `/`, so `http://a.com` and `http://a.com/` match
   - store the normalized form and redirect to it
5. What not to normalize:
   - `http` vs `https`: they can be different resources, and silently upgrading to https may break a link.
   - A trailing slash on a non-empty path: `/docs` and `/docs/` can be different pages on the server.
   - The order of query parameters, or the case of the path: both can change what the server returns.

Add risk tests for: a mixed-case `javascript:` scheme; a URL with user:password before the host; `http://a.com` and `http://a.com/` giving the same code; `http` and `https` giving different codes.

Open redirect: the scheme allowlist plus the rules above are the defence; phishing-domain blocking or a preview page stays out of scope.
