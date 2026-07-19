# Orion frontend architecture

## Architecture goals

Build Orion as a strict TypeScript Next.js App Router application with clear ownership boundaries. The frontend should preserve the Figma Make visual language without copying its single-component architecture or its mock state model.

Core decisions:

- App Router routes replace the prototype's in-memory `Screen` union.
- Server components are the default; client components are added only for forms, recording, charts, drawers, mutations, and other interactive state.
- TanStack Query owns remote server state and mutation lifecycles. It is not used for static route composition or local UI toggles.
- React Hook Form and Zod own form state and client validation. API payload/response schemas also use Zod at the network boundary.
- TanStack Table powers data-heavy lists where sorting/filtering/pagination is meaningful and all accessible chart data tables.
- shadcn/ui supplies accessible behavior primitives, customized through Orion semantic tokens.
- Lucide icons are used through a small shared icon layer and never as the only status signal.
- Tailwind CSS v4 consumes semantic CSS variables through `@theme inline`; page files do not contain one-off color or typography values.
- Feature fixtures remain isolated and replaceable. They never define API contracts.

## Proposed route map

### Public routes

| Route | Page | Notes |
|---|---|---|
| `/` | Landing | Public, design-system-led product overview with `/signup` and `/login` actions. |
| `/login` | Sign in | Public-only; authenticated users redirect to `/entries`. |
| `/signup` | Registration | Public-only; authenticated users redirect to `/entries`. |

### Protected routes

| Route | Navigation label | Purpose |
|---|---|---|
| `/entries` | Entries | Journal history and current processing states. |
| `/entries/new` | New Entry | Text and voice capture. Whether it remains a sidebar item is a product decision. |
| `/entries/[entryId]` | — | Entry detail and extracted-item review in context. |
| `/review` | Review | Pending idea and memory approval queue. |
| `/ideas` | Ideas | Approved ideas by default. |
| `/memories` | Memories | Approved extracted memories by default. |
| `/reflections` | Reflections | Cross-entry Hidden Drivers, Recurring Loops, and Inner Tensions. |
| `/journey` | Journey | Theme River, chapters, transformations, echoes, and evidence. |
| `/insights` | Insights | Theme composition and EMA. Required by the brief but missing from exported Make navigation. |
| `/settings/profile` | Profile | Identity/profile preferences. |
| `/settings/privacy` | — | Privacy and account deletion. |
| `/settings/themes` | — | Theme configuration, activation, and backfill status. |

Use route constants and typed route builders for dynamic paths. Do not scatter URL strings through components.

## Proposed folder structure

```text
.
├── docs/
│   ├── figma-audit.md
│   └── frontend-architecture.md
├── public/
│   └── fonts/                         # only after the Lora/Crimson decision
├── src/
│   ├── app/
│   │   ├── (public)/
│   │   │   ├── layout.tsx             # AuthLayout
│   │   │   ├── login/page.tsx
│   │   │   └── register/page.tsx
│   │   ├── (protected)/
│   │   │   ├── layout.tsx             # authenticated ProtectedAppLayout
│   │   │   ├── entries/
│   │   │   │   ├── page.tsx
│   │   │   │   ├── loading.tsx
│   │   │   │   ├── error.tsx
│   │   │   │   ├── new/page.tsx
│   │   │   │   └── [entryId]/page.tsx
│   │   │   ├── review/page.tsx
│   │   │   ├── ideas/page.tsx
│   │   │   ├── memories/page.tsx
│   │   │   ├── reflections/page.tsx
│   │   │   ├── journey/page.tsx
│   │   │   ├── insights/page.tsx
│   │   │   └── settings/
│   │   │       ├── layout.tsx
│   │   │       ├── profile/page.tsx
│   │   │       ├── privacy/page.tsx
│   │   │       └── themes/page.tsx
│   │   ├── error.tsx                  # uncaught route error
│   │   ├── global-error.tsx
│   │   ├── layout.tsx                 # fonts, metadata, Providers
│   │   ├── not-found.tsx
│   │   ├── page.tsx                   # session redirect
│   │   └── globals.css                # Tailwind v4 + Orion tokens
│   ├── components/
│   │   ├── ui/                        # shadcn primitives only
│   │   ├── layout/                    # shell, sidebar, mobile header, page shell
│   │   ├── states/                    # loading/empty/error/insufficient/offline
│   │   ├── data-display/              # status, theme, journal, evidence primitives
│   │   └── feedback/                  # confirm dialogs, announcer, toasts
│   ├── features/
│   │   ├── auth/
│   │   ├── entries/
│   │   ├── review/
│   │   ├── ideas/
│   │   ├── memories/
│   │   ├── reflections/
│   │   ├── journey/
│   │   ├── insights/
│   │   └── settings/
│   │       ├── profile/
│   │       ├── privacy/
│   │       └── themes/
│   ├── lib/
│   │   ├── api/
│   │   │   ├── client.ts              # auth headers, correlation IDs, errors
│   │   │   ├── errors.ts
│   │   │   └── pagination.ts
│   │   ├── auth/
│   │   │   ├── server.ts
│   │   │   └── client.ts
│   │   ├── query/
│   │   │   ├── client.ts
│   │   │   ├── keys.ts
│   │   │   └── providers.tsx
│   │   ├── routes.ts
│   │   ├── cn.ts
│   │   └── env.ts
│   ├── config/
│   │   ├── navigation.ts
│   │   ├── design-tokens.ts
│   │   ├── themes.ts                  # canonical eight-theme registry
│   │   └── status-variants.ts
│   ├── hooks/
│   │   ├── use-online-status.ts
│   │   └── use-reduced-motion.ts
│   ├── types/
│   │   └── common.ts
│   └── test/
│       ├── setup.ts
│       ├── render.tsx                 # provider-aware RTL render
│       ├── factories/
│       └── mocks/
├── e2e/
│   ├── auth.spec.ts
│   ├── entries.spec.ts
│   ├── review.spec.ts
│   ├── reflections.spec.ts
│   └── journey.spec.ts
├── components.json
├── next.config.ts
├── playwright.config.ts
├── postcss.config.mjs
├── tsconfig.json
├── vitest.config.ts
└── package.json
```

Inside each feature, use only the folders it needs:

```text
features/entries/
├── api/              # request functions and Zod wire schemas
├── components/
├── hooks/            # query/mutation hooks
├── model/            # domain types, adapters, view models
├── schemas/          # form schemas
├── testing/          # feature fixtures/factories, excluded from production paths
└── index.ts          # intentional public feature API
```

Avoid generic `utils.ts` dumping grounds and cross-feature imports into another feature's internals. Promote genuinely shared behavior to `components/` or `lib/`.

## Route and layout ownership

### Root layout

- Loads the confirmed sans/serif fonts with `next/font` or local assets.
- Applies the light-only semantic token theme.
- Mounts the TanStack Query provider, toast region, and global accessibility announcer.
- Contains no product shell and no user-specific data.

### Public layout

- Renders `AuthLayout` and brand treatment.
- Redirects active sessions away from auth pages.
- Does not mount protected navigation.

### Protected layout

- Performs the server-side session check. Client guards are UX only.
- Renders `ProtectedAppLayout` with desktop sidebar and mobile navigation.
- Supplies current-user summary and pending-review count through authenticated queries or prefetched data.
- Owns the skip link, main landmark, and navigation semantics.

### Settings layout

- Adds settings subnavigation without creating another visual card shell.
- Keeps profile, privacy, and theme configuration separately addressable.

### Pages

- Parse route params/search params.
- Prefetch route-critical queries when useful.
- Render one feature page composition.
- Do not define design tokens, network clients, reusable controls, or mock business logic.

## Component ownership

### Design-system primitives

`src/components/ui` contains shadcn-generated behavior primitives only. Orion variants are defined centrally with CSS variables and CVA where appropriate:

- Button and icon button: primary, secondary, ghost, destructive; 44px default and 36px compact visual height while preserving touch targets.
- Inputs: consistent 10px radius, error relationship, focus ring, disabled/read-only styling.
- Card: flat, bordered, interactive, and overlay variants; no arbitrary shadows.
- Badge/status/chip: pill only where semantically appropriate.
- Tabs versus segmented control: separate components because they have different semantics and visual behavior.
- Dialog/alert dialog/sheet/drawer: shared focus trap, return focus, accessible naming, reduced motion.
- Skeleton: composable editorial shapes, not route-specific hardcoded blocks.
- Table: semantic building blocks consumed by TanStack Table.

### Shared application components

These are product-wide compositions, not raw primitives:

- Shell: `ProtectedAppLayout`, `AppSidebar`, `MobileHeader`, `MobileNavSheet`, `BrandMark`, `UserMenu`.
- Page structure: `PageShell`, `PageHeader`, `SettingsNav`, `BackLink`.
- States: `RouteState`, `LoadingState`, `EmptyState`, `ErrorState`, `InsufficientDataState`, `OfflineBanner`.
- Status/data: `EntryStatusBadge`, `ThemeIndicator`, `ThemeChip`, `ThemeLegend`, `JournalExcerpt`, `EntryMeta`.
- Actions: `ApprovalActions`, `ResonanceControls`, `DateRangeControl`, `PaginationControls`.
- Evidence: `EvidenceDrawer`, `EvidenceItem`, `WhyThisTooltip`.
- Accessibility/feedback: `ScreenReaderAnnouncer`, `ConfirmDialog`, toast helpers.

### Feature components

Feature components and their ownership are listed in `docs/figma-audit.md`. Features may consume shared components and UI primitives but should not import another feature's private API. Cross-feature navigation uses routes, and shared backend entities use neutral types/adapters in `lib` only when their semantics truly match.

### Page-only components

Keep page-only components rare. A component becomes feature-level as soon as it contains interaction, state-specific rendering, a reusable content pattern, or test-worthy behavior. This prevents the new app from recreating the Make monolith one route at a time.

## Design tokens and Tailwind CSS v4

Define raw palette values once in `src/app/globals.css`, map them through `@theme inline`, and expose typed registries for semantic lookups.

Token groups:

- Surfaces: background, card, sidebar, muted, input, overlay.
- Text: foreground, muted foreground, inverse.
- Actions: primary, primary foreground, accent, destructive.
- Borders/focus: border, input border, ring.
- Status: neutral, processing, success, warning, destructive; each includes text, icon, and background/border treatment.
- Eight themes: stable values and labels.
- Typography roles: display through eyebrow, plus mobile adjustments.
- Spacing: approved 4–80px scale.
- Size: sidebar width, content max, text measures, touch target, controls, drawers.
- Radius: 8/10/14/16px and pill.
- Motion: 120–160ms hover/focus, 160–200ms filters/tabs, 200–240ms overlays, reduced-motion override.
- Elevation: none and one overlay shadow.

Rules:

- No arbitrary hex values in page or feature components.
- No arbitrary font families/sizes/weights in page files.
- Dynamic theme color comes from a typed `ThemeKey -> CSS variable` registry, not user/API-provided style strings.
- Status and theme concepts remain separate.
- Light mode is the only initial mode.

## Data architecture

### Network boundary

`lib/api/client.ts` handles base URL, bearer token, JSON/multipart differences, correlation IDs, timeout/cancellation, and normalized errors. It must never expose secrets or log journal content.

Every feature API function:

1. Defines a Zod wire schema.
2. Calls the shared client.
3. Parses the response.
4. Adapts wire data into a feature model/view model.
5. Returns typed data to a query hook.

Do not infer missing API fields from the Make fixtures. When the backend contract is unavailable, define an explicit `CONTRACT_PENDING` adapter boundary and keep the UI fixture behind it.

### TanStack Query

- Query keys are factories grouped by feature and include user, filters, date range, config, and pagination where relevant.
- Mutations invalidate or update the smallest relevant cache slice.
- Approval decisions use optimistic UI only if rollback and `409 already decided` behavior are fully specified; otherwise prefer mutation-pending UI followed by invalidation.
- Entry creation returns/uses an entry identity and lets the Entries/Detail query observe processing completion. Do not retain the prototype's `setTimeout` simulation in production.
- Polling is limited to documented processing/backfill states and stops on completion, failure, unmount, or lost auth.
- Route loading boundaries handle initial navigation; inline skeletons handle filter/page changes.

### Forms

Use React Hook Form plus Zod for:

- login and registration;
- text entry;
- voice-upload metadata/validation where applicable;
- profile;
- deletion confirmation;
- theme configuration.

Server/API validation is mapped back to specific fields or a form-level error region. All errors are associated with controls and announced.

Voice recording state is a dedicated state machine, not a cluster of booleans:

```text
idle -> requesting_permission -> recording <-> paused
recording/paused -> stopping -> uploading -> transcribing -> accepted
any active state -> recoverable_error | terminal_error
```

The exact retry transitions must follow the backend/product contract.

### Tables and charts

TanStack Table should power Review/Ideas/Memories only if the final design needs sortable/filterable columns; editorial row lists remain simpler semantic lists. It always powers chart data alternatives where column definitions and responsive rendering benefit from it.

Charts are client components loaded only on routes that need them. Each chart is wrapped by a shared frame containing:

- accessible title/description;
- textual summary;
- stable legend with labels;
- visual canvas/SVG;
- keyboard-accessible interactions where applicable;
- disclosure containing a semantic data table.

## State architecture

Route states use a discriminated union instead of overlapping booleans:

```ts
type ViewState<T> =
  | { status: "loading" }
  | { status: "error"; error: AppError }
  | { status: "empty" }
  | { status: "insufficient"; reason: string }
  | { status: "success"; data: T };
```

Processing/failure for an individual entry or job belongs to the entity model and can render inside a successful list. Offline status is orthogonal and comes from the shared online-status hook plus actual query errors; browser `navigator.onLine` alone is not treated as proof of API reachability.

Normalize API failures into safe categories such as unauthenticated, forbidden, not found, conflict, validation, payload too large, rate limited, dependency unavailable, offline/network, and unknown. Recovery buttons are rendered only when the contract defines a valid action.

## Navigation architecture

`src/config/navigation.ts` is the only primary-navigation source. Each item defines:

- stable key;
- user-facing label;
- route or route builder;
- Lucide icon component;
- active-match behavior;
- access/feature flag;
- optional badge query key.

Desktop and mobile navigation render the same item model. `usePathname` determines the active state; pages do not set navigation state. Entry detail keeps Entries active. Settings child routes keep Profile/Settings active.

## Accessibility requirements

- Skip link targets the protected layout's `main` element.
- One `h1` per route and semantic heading order.
- Visible `focus-visible` styling on every interactive element.
- 44px touch targets at 320px and above.
- Icon-only controls have accessible names and tooltips where helpful.
- Statuses combine label, icon, and/or shape; never color alone.
- Dialogs/drawers trap focus, close predictably, and restore focus to their trigger.
- Forms connect descriptions/errors with `aria-describedby` and announce failed submissions.
- Mutations and processing updates use polite live regions.
- Exact journal evidence remains selectable and clearly distinguished from Orion interpretation.
- Charts have summaries and data tables.
- Motion is non-essential and suppressed under `prefers-reduced-motion`.
- Mobile layouts support 200% zoom/reflow without losing actions.

## Testing strategy

### Vitest and React Testing Library

Test behavior at the smallest stable boundary:

- token-backed variant and accessibility contracts for shared components;
- forms: valid submit, field errors, API errors, disabled/pending behavior;
- navigation manifest and active-route matching;
- entry/approval/backfill state transitions;
- adapters and Zod schemas with valid/invalid fixtures;
- query hooks with MSW-style request mocks;
- Reflections resonance and evidence drawer behavior;
- Journey range/chapter/tab/evidence interactions;
- loading, empty, error, insufficient, processing, failed, and offline rendering.

Avoid snapshots for full pages. Prefer roles, names, state text, and user-visible outcomes.

### Playwright critical routes

Critical browser coverage:

1. Public redirect, sign in, protected redirect, and logout.
2. Create a text entry, observe processing, open entry detail.
3. Voice permission denial and upload/limit error path using controlled mocks.
4. Approve and reject review items, including a `409` conflict.
5. Reflections populated/insufficient states and evidence drawer focus behavior.
6. Journey range selection, chapter tabs, data-table alternative, and mobile evidence sheet.
7. Settings destructive deletion confirmation without executing real deletion in shared environments.
8. Responsive smoke tests at 320, 768, 1024, and 1440px with no page-level horizontal overflow.

Use deterministic API fixtures and test IDs only where accessible roles/names cannot uniquely select data-visualization elements.

## Implementation order

1. **Resolve blocking design/contract ambiguities.** Confirm serif font, sidebar width, final primary navigation, settings route split, Insights/theme-config scope, and recovery actions/error copy.
2. **Scaffold the platform.** Next.js App Router, strict TypeScript, Tailwind v4, shadcn configuration, Vitest/RTL, Playwright, lint/typecheck, environment validation.
3. **Build tokens and primitives.** Fonts, semantic colors, typography roles, spacing/radii/motion, Button/Input/Card/Tabs/SegmentedControl/Sheet/Dialog/Skeleton/Table.
4. **Build providers and layouts.** Root providers, public layout, protected auth check, shared shell, navigation manifest, PageShell/PageHeader, settings layout.
5. **Build shared states and data boundaries.** API client, normalized errors, query keys/provider, route states, offline banner, status system, evidence drawer, accessible chart frame.
6. **Implement auth.** Login/register forms, redirects, session refresh, error/rate-limit/offline behavior, route tests.
7. **Implement the entry vertical slice.** Entries list, text composer, voice state machine, processing/failure, detail, themes, extracted items. This proves routing, forms, queries, responsive layout, and states.
8. **Implement Review, Ideas, and Memories.** Shared saved-item models, approval actions, filters/pagination, conflict handling.
9. **Implement Reflections.** Adapter/view model, all route states, narrative sections, resonance, shared evidence drawer.
10. **Implement Journey.** Long-range query model, Theme River, chapter rail/tabs, table alternative, boundary/evidence interactions, responsive transformations.
11. **Implement Insights and Settings after scope confirmation.** Reuse chart frame/theme registry; add profile/privacy/theme configuration and backfill state machine.
12. **Hardening pass.** Accessibility, 320/768/1024/1440 visual verification, reduced motion, offline/HTTP error matrix, unit/integration coverage, and critical Playwright routes.

Each feature slice is complete only when its populated state, required non-happy states, responsive behavior, accessibility contract, and tests are delivered together.

## Explicit exclusions for the planning phase

- No application pages or route files are implemented yet.
- No Figma-generated `App.tsx` code is copied into the repository.
- No page-specific colors, font values, radii, or shadows are introduced.
- No API response fields or recovery actions are invented.
- No dark mode is planned for v1.
- No prototype state-switching controls or design-review gallery are included in production routing.

## Decisions needed before implementation

1. Lora or Crimson Pro for editorial text.
2. Sidebar width: current design-system token (264–296px) or another approved value.
3. Whether New Entry remains in global navigation.
4. Whether Insights is a primary navigation item.
5. Whether Profile, Privacy, and Themes are separate settings routes as proposed.
6. Whether the theme-config/backfill experience is in the first frontend milestone.
7. Approved frontend URL spellings if the proposed route map is not acceptable.
8. Final API/OpenAPI contract and user-facing recovery actions for all required error states.
