# Checkpoint 08 — Final frontend audit

Date: 2026-07-19

## Outcome

The complete frontend was audited against the Orion architecture and design-system rules. The pass removed confirmed duplication, restored feature/service boundaries, consolidated mock state, corrected accessibility and responsive-state defects, and removed dead code without adding product features.

The approved Figma appearance and semantic design tokens remain the visual contract. Changes to screenshot baselines are limited to corrected semantic markup, authenticated profile identity, and the resulting browser text/layout rendering.

## Changes made

- Added one `DataViewStatus` composition and one `getDataViewStatus` state resolver for initial loading, initial error, preserved-data refresh error, refreshing, and ready states.
- Added one shared `RefreshButton` for the repeated refresh action used by data views.
- Moved repository calls and TanStack Query behavior out of screens into feature query hooks for entries, approvals, reflections, journey, profile, and saved items.
- Added `useCollectionControls` and shared page-size constants for repeated search, filter-reset, and pagination behavior.
- Consolidated entry, approval, and saved-item fixtures behind one typed in-memory Orion store so review decisions update the queue, navigation count, entry detail, and saved-item views coherently.
- Made the protected navigation's review count query-backed instead of hardcoded.
- Made mock profiles derive from the authenticated user and kept the client auth identity synchronized after a profile-name update.
- Centralized status types, labels, and visual tones in `src/config/status.ts`, and centralized recurring data-view error copy in `src/config/messages.ts`.
- Introduced shared record types that keep presentational models independent from repository response ownership and remove private cross-feature type imports.
- Replaced repeated repository delay helpers with `simulateLatency`.
- Removed the unused `RouteScaffold` component and its export.
- Renamed the typography registry key consistently to `reflectiveStatement` while retaining the approved `type-reflection-card-statement` CSS utility.
- Corrected the Journey six-month and one-year bucket counts and added regression coverage.
- Prevented New Entry mode changes while voice recording is active and added regression coverage for the control state.
- Serialized Playwright execution while the mock repositories use one shared process-local store. This removes cross-test mutation and mock-auth timing flakes until backend data is user-scoped.

## Duplication removed

| Area                     | Consolidation                                                                                         |
| ------------------------ | ----------------------------------------------------------------------------------------------------- |
| Loading and error states | Repeated query-state branches now render through `DataViewStatus`.                                    |
| Refresh actions          | Repeated refresh buttons now use `RefreshButton`.                                                     |
| Search and pagination    | Entries, approvals, and saved-item screens use `useCollectionControls` and shared page sizes.         |
| Status metadata          | Entry, approval, saved-item, extracted-item, and chapter status metadata comes from one registry.     |
| Error messages           | Recurring data-view copy comes from one message registry; feature-specific explanations remain local. |
| Mock records             | Entry, approval, and saved-item repositories use one canonical store and shared record types.         |
| Query behavior           | Repository calls and invalidation rules are contained in feature query hooks.                         |
| Mock latency             | Repository-specific wait functions were replaced by one helper.                                       |
| Dead components          | The unreferenced `RouteScaffold` component was removed.                                               |
| Documentation            | The duplicated Reflections section heading in the Figma deviation log was merged into one hierarchy.  |

The route registry remains the only production source for route paths, labels, authentication requirements, sidebar visibility, and navigation icons. Route literals found by the audit are limited to tests that assert browser URLs.

## Remaining intentional exceptions

- `theme-river.tsx` remains a large, cohesive accessible visualization. It owns one tightly coupled SVG coordinate system and accompanying data table; splitting it would create one-consumer abstractions without reducing domain complexity.
- The generic `DataTable` remains a substantial component because sorting, filtering, selection, pagination, state rendering, and its mobile representation form one public contract.
- The development design-system catalog is intentionally large and route-only. Its repeated examples are visual demonstrations, not application components.
- Route-specific empty, processing, and explanatory copy remains feature-owned because the user meaning differs even when the shared visual state component is the same.
- shadcn primitives in `src/components/ui` retain upstream behavior-generic utility classes. Feature styling continues to be applied through Orion wrappers rather than by modifying primitives.
- Reflections feedback and Journey interpretation data remain replaceable mock behavior because no approved persistence or longitudinal-analysis API exists yet.
- Playwright uses one worker while repositories share process-local mutable fixtures. Restore parallel workers only after test data can be isolated per authenticated user or worker.
- No direct dependency was removed: every package declared in `package.json` has a current architecture or tooling consumer.

## Test results

| Check                        | Result                                                                         |
| ---------------------------- | ------------------------------------------------------------------------------ |
| `npm run format:check`       | Passed — all checked files use Prettier formatting.                            |
| `npm run lint`               | Passed — ESLint emitted no warnings; design-system policy checks passed.       |
| `npm run typecheck`          | Passed — Next route generation and strict TypeScript completed without errors. |
| `npm test -- --reporter=dot` | Passed — 20 test files, 97 tests.                                              |
| `npm run test:e2e`           | Passed — 33 Chromium route and responsive tests.                               |
| Circular import scan         | Passed — no circular source imports found.                                     |

The first final parallel Playwright run exposed a nondeterministic mock-auth/shared-store timing failure. A repeat passed all 33 tests, and the suite was then made deterministic with one worker before the final recorded run.

## Build result

`npm run build` passed with Next.js 16.2.10. All public, authentication, protected, development, and health routes compiled; TypeScript, page-data collection, and static generation completed successfully.

## Figma deviations

- No new visual design exception was introduced by this audit.
- Journey screenshot baselines changed after invalid nested interactive markup was replaced by one valid card button and explicit keyboard focus styling.
- Profile screenshot baselines now show the authenticated mock user instead of an unrelated fixed fixture identity.
- Reflections baselines changed only by browser-level rendering pixels after the shared typography/status cleanup.
- Protected Journey, Profile, and Reflections source screenshots are not present in the Figma Make export, so their existing written-spec validation remains the available reference.

The complete known deviation record remains in `docs/figma-deviations.md`.

## Accessibility issues

Resolved during this audit:

- Removed invalid nested interactive/card markup from the Journey chapter rail.
- Added explicit visible keyboard focus treatment to Journey river and chapter-boundary controls.
- Ensured color-backed status and theme treatments retain visible text labels.
- Kept New Entry mode controls unavailable while microphone recording is active, preventing hidden active-capture state.
- Preserved mobile overflow checks at 320px and responsive shell behavior in Playwright.

No known blocking accessibility regression remains in the audited flows. Automated route tests cover semantics and keyboard-relevant controls, but a dedicated axe-core rule set and assistive-technology manual pass are still recommended before release.

## Recommended next backend-integration steps

1. Replace each mock repository behind its existing interface; keep screens and presentational components unchanged.
2. Scope entries, approvals, saved items, profiles, reflections, and journey data to the authenticated user so request and test isolation are guaranteed.
3. Provide one atomic approval command whose response identifies the updated entry, pending-review count, and created saved item; invalidate the existing feature query keys from that response.
4. Add current-user profile read/update endpoints and synchronize authoritative auth metadata after a successful update.
5. Add persistence endpoints for reflection feedback and longitudinal Journey aggregates, including stable evidence identifiers and confidence metadata.
6. Standardize backend error envelopes against the existing application error normalization and distinguish initial-load failures from refresh failures.
7. Add Server Component prefetch/dehydration for protected first loads only after the real repositories and authorization rules are available.
