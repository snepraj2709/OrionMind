# Orion design exceptions

## 2026-07-19 — Lora italic Orion wordmark

- **Owner:** Frontend
- **Affected files:** `src/components/layout/brand-mark.tsx`, `src/config/design-system.ts`, `src/styles/typography.css`
- **Rule:** Lora was previously limited to reflective and long-form personal writing, with no approved italic interface role.
- **Reason:** The confirmed Login and Signup brand treatment uses Lora Italic for the prominent `Orion` logo text and nowhere else.
- **Alternatives considered:** Keeping the Inter component-title treatment was rejected because it does not express the approved wordmark.
- **Review condition:** Revisit only if Orion's auth branding changes. Default application branding, feature copy, and interface copy must not reuse this exception.

When an exception is necessary, document its date, owner, affected files, design-system rule, reason, alternatives considered, and removal or review condition before merging the implementation.
