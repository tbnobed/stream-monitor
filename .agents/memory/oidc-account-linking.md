---
name: OIDC account linking
description: Why SSO login must bind strictly by subject, never by email, to avoid account takeover
---

# OIDC / SSO account linking

Authenticate SSO logins **strictly by the stable `(issuer/)sub` claim**. A given
`sub` maps to exactly one local account. Never look up or link an existing
account by the token's `email` claim during login, and never reassign an
existing user's `oidc_subject` from the token.

**Why:** linking by email lets any SSO identity take over an existing local
account — including admin — just by presenting a matching address (and the IdP
may not even verify the address). This was a real vulnerability caught in code
review on the OTT Stream Monitor SSO callback.

**How to apply:** in the OIDC callback, query the user by `oidc_subject == sub`
only. If none, auto-provision a fresh account. Treat the `email` claim as
untrusted unless `email_verified` is true, and even then use it only for
profile backfill, never for authentication/linking decisions.
