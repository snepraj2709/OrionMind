# Orion design exceptions

## 2026-07-21 — Figma landing-page desktop geometry

- **Owner:** Frontend
- **Affected files:** `src/features/landing/landing-page.tsx`, `src/features/landing/landing-visuals.tsx`, `src/features/landing/landing.module.css`
- **Rule:** `PageShell` normally caps desktop inline padding at 56px, feature pages normally use only shared spacing, sizing, and typography stops, and `BrandMark` is normally the only brand treatment.
- **Reason:** The approved landing-page Figma frame is a fixed 1440×8797 composition with 80px desktop gutters, section-specific heights and offsets, display sizes between the shared typography roles, and a compact dot-and-wordmark lockup. The landing route needs those source dimensions, type sizes, and lockup to reproduce the supplied design exactly.
- **Alternatives considered:** Using the standard 56px shell, content-driven section heights, shared type roles without landing overrides, and 48px image-based `BrandMark` was rejected because it visibly changes every horizontal alignment, the complete page height, text wrapping, and both brand placements from the approved Figma frame.
- **Review condition:** Keep the exception scoped to the public `/` landing page. Remove it if the source Figma is migrated to the standard `PageShell` geometry or if a shared marketing shell adopts these exact dimensions.

## 2026-07-20 — Lora italic Orion wordmark

- **Owner:** Frontend
- **Affected files:** `src/components/layout/brand-mark.tsx`, `src/config/design-system.ts`, `src/styles/typography.css`
- **Rule:** Lora was previously limited to reflective and long-form personal writing, with no approved italic interface role.
- **Reason:** The shared transparent symbol retains the confirmed Login and Signup Lora Italic `Orion` wordmark and uses it nowhere else.
- **Alternatives considered:** Keeping the Inter component-title treatment was rejected because it does not express the approved wordmark.
- **Review condition:** Revisit only if Orion adopts a complete image-based lockup that includes the brand name. Feature and interface copy must not reuse this exception.

When an exception is necessary, document its date, owner, affected files, design-system rule, reason, alternatives considered, and removal or review condition before merging the implementation.
