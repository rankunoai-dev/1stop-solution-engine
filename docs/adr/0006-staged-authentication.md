# ADR 0006 — Staged staff authentication: email codes now, Entra ID later

**Status**: Accepted (owner, 2026-09-30) · **Decision log**: D-17, D-21 · **Risk**: R-26

## Context
Staff identity will be Microsoft Entra ID, but testing runs on a Gmail account. A login is needed from R0.

## Decision
- R0–R3: allowlisted emails; a 6-digit one-time code sent by email (hashed, 10-minute expiry, 5 attempts, rate-limited); server-side sessions in an HttpOnly cookie; CSRF header on mutating routes; roles `staff` / `admin`.
- R2 widget: per-tool keys + allowed origins, then tool-signed user tokens.
- R4: "Sign in with Microsoft" (Entra ID, OIDC) beside or replacing email codes.
- Users are keyed by email from day one.

## Consequences
No passwords to store. Login depends on email delivery from the test Gmail; the R4 migration checklist removes that dependency (R-26).
