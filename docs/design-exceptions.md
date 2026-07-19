# Orion design exceptions

## 2026-07-20 — Lora italic Orion wordmark

- **Owner:** Frontend
- **Affected files:** `src/components/layout/brand-mark.tsx`, `src/config/design-system.ts`, `src/styles/typography.css`
- **Rule:** Lora was previously limited to reflective and long-form personal writing, with no approved italic interface role.
- **Reason:** The shared transparent symbol retains the confirmed Login and Signup Lora Italic `Orion` wordmark and uses it nowhere else.
- **Alternatives considered:** Keeping the Inter component-title treatment was rejected because it does not express the approved wordmark.
- **Review condition:** Revisit only if Orion adopts a complete image-based lockup that includes the brand name. Feature and interface copy must not reuse this exception.

When an exception is necessary, document its date, owner, affected files, design-system rule, reason, alternatives considered, and removal or review condition before merging the implementation.
