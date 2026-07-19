# Orion Figma Make audit

## Audit scope and evidence

Source inspected: [Orion Web App — Figma Make](https://www.figma.com/make/HOiNxAIfOWM9wtQ5WSG7GC/Orion-Web-App--Copy-?t=SQwASoFdGSUfQO4Q-1), file key `HOiNxAIfOWM9wtQ5WSG7GC`, Make root `0:1`.

This audit is based on the Figma integration's Make source manifest and the following source artifacts:

- `src/app/App.tsx`
- `design_system.md`
- `src/styles/theme.css` and the remaining style entrypoints
- the bundled Reflections and Journey design specifications
- the bundled Orion journaling product requirements
- the generated shadcn/ui source inventory
- the Make image-asset manifest

The Make export is a design artifact, not production code. Its `App.tsx` is a single, state-driven React prototype. The exported file is incomplete: it contains a literal truncation marker in the Journey implementation and references screen components that are absent from the source manifest. A forced-code request returned the same resource. The interactive Make preview could not be opened because no browser session is available in this workspace. Consequently:

- Screen names, navigation, top-level state, tokens, and shell behavior below are source-verified.
- Reflections and Journey details are source- and specification-verified.
- Fine-grained layouts for the missing screen component bodies are requirements-derived and marked accordingly.
- Nothing unverifiable is treated as a frozen product or API contract.

## Product and visual direction

Orion is a quiet, light-mode-first journaling product. It should feel editorial and reflective rather than like a productivity dashboard. Hierarchy is created with typography, spacing, thin borders, and small surface shifts. Ordinary cards do not use shadows. Color is restrained and never the only status signal.

The generated theme file contains a dark-mode passthrough, but the Make design brief explicitly says light mode only. Do not ship a theme switcher or dark-mode UI unless that scope changes.

## Navigation structure

The Make prototype uses a `Screen` union and local React state instead of URLs. Its source-verified desktop/mobile navigation order is:

1. Entries
2. New Entry
3. Review
4. Ideas
5. Memories
6. Reflections
7. Journey
8. Profile

`Review` shows a pending-item count. Selecting an entry opens an entry-detail state. Auth is outside the protected shell. Logout is available in the sidebar user row and Profile.

Desktop uses a persistent left sidebar. Below 1024px the design system says the sidebar collapses; the prototype renders a fixed 56px mobile header and a left-side overlay menu. The same navigation data must drive both presentations.

## Screen inventory

Routes are proposed production routes, not routes present in the Make prototype.

| Screen | Target route | Access | Shared layout | Shared components | Required states |
|---|---|---|---|---|---|
| Sign in | `/login` | Public | `AuthLayout` | `BrandMark`, `AuthForm`, form fields, `FormError` | idle, submitting, invalid fields, invalid credentials, rate limited, provider unavailable, offline |
| Register | `/register` | Public | `AuthLayout` | `BrandMark`, `AuthForm`, password guidance, `FormError` | idle, submitting, validation error, existing account/conflict, rate limited, provider unavailable, offline |
| Entries | `/entries` | Protected | `ProtectedAppLayout` + `PageShell` | `PageHeader`, `EntryList`, `EntryRow`, `EntryStatusBadge`, `ThemeIndicators`, `RouteState` | loading, empty, populated, processing row, failed row, retrying, pagination/loading more, error, offline |
| New text/voice entry | `/entries/new` | Protected | `ProtectedAppLayout` + focused `PageShell` | `EntryComposer`, `TextEntryForm`, `VoiceRecorder`, `RecordingControls`, `FormError`, `LeavePageDialog` | text idle/invalid/submitting; voice permission denied/recording/paused/uploading/transcribing; payload too large; processing accepted; error; offline |
| Entry detail | `/entries/[entryId]` | Protected | `ProtectedAppLayout` + `PageShell` | `BackLink`, `JournalEntry`, `EntryStatusBadge`, `ThemeSummary`, `ExtractedItemList`, `ApprovalActions` | loading, processing, completed, failed, retrying, not found, error, offline, pending/approved/rejected extracted items |
| Review queue | `/review` | Protected | `ProtectedAppLayout` + `PageShell` | `PageHeader`, `ReviewQueue`, `ReviewCard`, `ApprovalActions`, filters, pagination | loading, empty, populated, deciding, decided, conflict/already decided, error, offline |
| Ideas | `/ideas` | Protected | `ProtectedAppLayout` + `PageShell` | `PageHeader`, `SavedItemList`, `SavedItemRow`, filters, pagination | loading, empty, populated, error, offline |
| Memories | `/memories` | Protected | `ProtectedAppLayout` + `PageShell` | `PageHeader`, `SavedItemList`, `SavedItemRow`, filters, pagination | loading, empty, populated, error, offline |
| Reflections | `/reflections` | Protected | `ProtectedAppLayout` + `PageShell` | `ReflectionHeader`, `DateRangeControl`, `AnchorNav`, `HiddenDriverCard`, `RecurringLoop`, `InnerTensionCard`, `FocusExperimentCard`, `ResonanceControls`, `EvidenceDrawer` | loading, API error, no entries, insufficient history, populated, evidence open, user-rejected insight |
| Journey | `/journey` | Protected | `ProtectedAppLayout` + `PageShell` | `JourneyHeader`, `DateRangeControl`, `LongRangeSummary`, `ThemeRiver`, `ThemeLegend`, `ChapterRail`, `ChapterDetailTabs`, `BoundaryPopover`, `EvidenceDrawer`, chart data table | loading, API error, no entries, insufficient data, emerging chapter, populated, no pattern echoes, evidence open |
| Profile | `/settings/profile` | Protected | `ProtectedAppLayout` + `SettingsLayout` | `SettingsNav`, `ProfileForm`, `FormError`, `ConfirmDialog` | loading, saved, dirty, submitting, validation error, API error, offline, signed out |
| Privacy and account deletion | `/settings/privacy` | Protected | `ProtectedAppLayout` + `SettingsLayout` | `PrivacyPanel`, `DeleteAccountDialog`, password/confirmation form | loading, idle, deleting, deletion error, deleted/signed out |
| Theme configuration and backfill | `/settings/themes` | Protected | `ProtectedAppLayout` + `SettingsLayout` | `ThemeConfigForm`, `ThemeListEditor`, `ActivationDialog`, `BackfillProgress` | loading, empty/default, editing, invalid, activating, conflict, backfill queued/running/completed/failed/stale, offline |
| Insights | `/insights` | Protected | `ProtectedAppLayout` + `PageShell` | `PageHeader`, `DateRangeControl`, `ThemeCompositionChart`, `ThemeEmaChart`, `ThemeLegend`, chart data tables | loading, no entries, insufficient data, populated, API error, offline |

The last three feature surfaces are required by the bundled design/product briefs but are not separate values in the exported Make `Screen` union. Profile may have intended to contain privacy/deletion, while Insights and theme configuration/backfill are missing from the exported navigation. This must be resolved before those routes are treated as final.

The prototype-only `Design Review`/handoff gallery requested by the original Make brief is not a production page and should not be included in the application unless a separate internal review route is explicitly requested.

## Layout patterns

### Auth layout

- Outside the protected shell.
- Calm centered form with Orion branding and constrained form measure.
- Sign-in and registration are two modes in the prototype; production uses separate routes so browser history, validation, and testing are deterministic.

### Protected application shell

- Persistent desktop sidebar from 1024px upward.
- Collapsed navigation below 1024px with a top bar and modal navigation sheet.
- Sidebar width token: `clamp(264px, 18vw, 296px)` in the design system. The prototype still hardcodes `w-56`/`w-64`; production should use the token.
- Main content must use `min-width: 0` and `width: 100%` to prevent chart/table overflow.
- One navigation manifest must supply label, route, icon, visibility, active matching, and optional badge data.

### Page shell

Every primary protected route uses:

```css
width: 100%;
max-width: 1440px;
margin-inline: auto;
padding-inline: clamp(20px, 3.5vw, 56px);
padding-block: clamp(28px, 4vw, 56px);
```

Do not constrain entire pages with `max-w-xl`/`max-w-3xl`. Constrain readable text inside full-width layouts to 68ch for reflective statements and 80ch for journal excerpts.

### Page header

- Desktop: title/subtitle on the left; actions and filters top-aligned on the right.
- Mobile: controls stack below the title; segmented controls may scroll horizontally.
- Header-to-content gap is 32–48px.

### List pages

Entries, Ideas, Memories, and Review share full-width rows or restrained cards, consistent metadata, dividers, empty/loading/error treatments, and pagination. Journal excerpts use the serif face; controls and metadata stay sans-serif.

### Reflective analysis pages

Reflections tells one vertical story: Hidden Drivers, Recurring Loops, Inner Tensions, then an optional Focus card. Journey uses progressive disclosure: summary, Theme River, chapter rail, one selected chapter tab, then evidence.

## Typography

The source-backed design system defines Inter for interface text and Lora for journal excerpts, chapter titles, and major reflective statements.

| Role | Size / line height | Weight | Family |
|---|---:|---:|---|
| Display | 40 / 48 | 600 | Inter |
| Page title | 32 / 40 | 600 | Inter |
| Section title | 24 / 32 | 600 | Inter |
| Component title | 20 / 28 | 600 | Inter |
| Reflective statement | 24 / 38 | 500 | Lora |
| Journal excerpt | 18 / 30 | 400 | Lora |
| Body large | 18 / 28 | 400 | Inter |
| Body | 16 / 24 | 400 | Inter |
| Navigation | 16 / 24 | 500 | Inter |
| Button | 15 / 20 | 600 | Inter |
| Body small | 14 / 20 | 400 | Inter |
| Metadata | 14 / 20 | 500 | Inter |
| Eyebrow | 12 / 16 | 600 | Inter, uppercase, 0.08em tracking |

Mobile page titles become 28/36; section titles 22/30; reflective statements 21/34; journal excerpts 17/28. Only weights 400, 500, and 600 are permitted.

Ambiguity: the older Make brief says Crimson Pro, while the current `design_system.md` and `theme.css` say Lora and the font file is effectively empty. Treat Lora as the latest source-backed decision, but confirm before installing fonts.

## Color system

### Semantic tokens

| Token | Value | Use |
|---|---|---|
| background | `#F7F5EF` | warm ivory canvas |
| card | `#FCFBF7` | raised/contained surface without ordinary shadow |
| sidebar | `#F1EEE5` | shell navigation surface |
| secondary / muted | `#EBE6DA` | selected/quiet controls |
| input background | `#EDE8DF` | input fill |
| foreground | `#20212A` | primary text |
| muted foreground | `#6F6B61` | secondary text |
| primary | `#293F78` | primary action/deep navy |
| primary foreground | `#F7F5EF` | text on primary |
| accent | `#71917E` | muted sage |
| border | `#DDD8CC` | one-pixel beige border |
| destructive | `#A9534D` | destructive/error action |

### Stable eight-theme palette

Career `#8B7085`; Money `#B28D48`; Health `#71917E`; Love Life `#C78488`; Family & Friends `#7086A7`; Personal Growth `#C47D67`; Fun & Recreation `#9A83A5`; Home & Lifestyle `#8D877B`.

The prototype also defines a five-theme chart palette and repeats raw theme hex values in JSX. Production must expose only the canonical eight-theme map and semantic aliases. Status colors must be semantic tokens, not borrowed theme colors.

## Spacing, borders, radii, and elevation

Spacing follows an 8px base with approved stops at 4, 8, 12, 16, 24, 32, 40, 48, 64, and 80px.

- Small controls/chips: 8px radius.
- Buttons/inputs: 10px radius.
- Cards: 14px radius.
- Drawers/large temporary surfaces: 16px radius.
- Pills: 999px only for chips and badges.
- Borders: one pixel, semantic border token.
- Ordinary cards: no shadow.
- Overlays/drawers: at most one soft, low-opacity elevation token.

The prototype mixes `rounded`, `rounded-lg`, `rounded-xl`, `rounded-full`, arbitrary colors, and ad-hoc opacity values. These are reference behavior, not acceptable production token usage.

## Responsive behavior

Breakpoints from the source design system:

- Mobile: below 768px.
- Tablet: 768–1023px.
- Desktop: 1024–1439px.
- Wide desktop: 1440–1919px.
- Ultrawide: 1920px and above, centered inside the 1440px maximum.

Required checks: 320/375px, 768px, 1024px, and 1440px.

Transformations:

- Sidebar becomes a menu below 1024px.
- Header actions stack on mobile.
- Long tab and segmented-control rows become horizontally scrollable without hiding functionality.
- Reflections' two-column recurring-loop region becomes a vertical stack; the loop itself becomes vertical.
- Evidence drawers become full-screen sheets on mobile.
- Journey's legend, chapter rail, and four tabs scroll horizontally.
- Journey's streamgraph remains full width on tablet, becomes pannable on mobile, and is approximately 300–360px high on desktop.
- Journey's Transformation Arc becomes vertical on mobile.
- Charts require a textual summary and accessible data-table alternative.
- No primary workflow may require horizontal page scrolling at 320px; only explicitly scrollable inner regions may scroll.

## State language and behavior

All route states preserve the page header and approximate final layout.

- Loading: editorial skeletons shaped like the eventual content, not generic boxes or full-page spinners.
- Empty: serif headline, one sentence, and a direct action; no large illustration.
- Error: concise explanation and Retry; no stack trace.
- Insufficient data: state the threshold plainly and invite continued journaling.
- Processing: keep the created entry visible, label it with text and icon, and update it without page replacement.
- Failed: explain that processing failed and offer the approved retry/recovery action when the contract defines one.
- Offline: persistent, non-blocking status plus disabled/mutation-safe controls; queued behavior must not be invented.
- Dynamic changes: announced through a polite live region.

## Component inventory

### Design-system primitives

- `Button`, `IconButton`
- `Input`, `Textarea`, `Label`, `FormField`, `FormMessage`
- `Card` with restrained variants
- `Badge`, `StatusBadge`, `ThemeChip`
- `Tabs`, `SegmentedControl`
- `Dialog`, `AlertDialog`, `Sheet`, `Drawer`
- `DropdownMenu`, `Tooltip`, `Popover`
- `Separator`, `ScrollArea`, `Skeleton`, `Progress`
- `Table` primitives for TanStack Table and chart alternatives
- `Toast`/`Sonner` for non-critical confirmations
- `VisuallyHidden`, focus and live-region helpers

Only primitives actually used by a feature should be added; the Make manifest's full shadcn catalog is not a requirement to install all components.

### Shared application components

- `AuthLayout`, `ProtectedAppLayout`, `SettingsLayout`
- `AppSidebar`, `MobileHeader`, `MobileNavSheet`, `BrandMark`, `UserMenu`
- `PageShell`, `PageHeader`, `BackLink`
- `RouteState`, `LoadingState`, `EmptyState`, `ErrorState`, `InsufficientDataState`
- `OfflineBanner`, `MutationStatus`, `ScreenReaderAnnouncer`
- `DateRangeControl`, `FilterBar`, `PaginationControls`
- `JournalExcerpt`, `EntryMeta`, `EntryStatusBadge`
- `ThemeIndicator`, `ThemeChip`, `ThemeLegend`
- `ApprovalActions`, `ResonanceControls`
- `EvidenceDrawer`, `EvidenceItem`, `WhyThisTooltip`
- `ConfirmDialog`

### Feature components

- Auth: `AuthForm`, `PasswordField`.
- Entries: `EntryList`, `EntryRow`, `EntryComposer`, `TextEntryForm`, `VoiceRecorder`, `RecordingControls`, `EntryDetail`, `ThemeSummary`, `ExtractedItemList`.
- Review: `ReviewQueue`, `ReviewCard`, `ReviewFilters`.
- Ideas/Memories: `SavedItemList`, `SavedItemRow`.
- Reflections: `ReflectionHeader`, `ReflectionAnchorNav`, `HiddenDriverCard`, `RecurringLoop`, `LoopStep`, `InnerTensionCard`, `FocusExperimentCard`.
- Journey: `JourneyHeader`, `LongRangeSummary`, `ThemeRiver`, `ChapterRail`, `ChapterCard`, `ChapterDetail`, `ChapterTabs`, `ChapterDnaPanel`, `TransformationArc`, `PatternEchoes`, `CarryForward`, `BoundaryPopover`.
- Insights: `ThemeCompositionChart`, `ThemeEmaChart`, `ChartDataTable`.
- Settings: `ProfileForm`, `PrivacyPanel`, `DeleteAccountDialog`, `ThemeConfigForm`, `ThemeListEditor`, `BackfillProgress`.

### Page-only components

Page files should compose feature components and own route metadata, params, and route-level prefetching only. Acceptable page-local pieces are one-off static copy blocks or a composition wrapper that has no cross-route reuse. Forms, states, cards, drawers, tables, and visual tokens are never page-only.

## Duplicated Make patterns to extract

1. The desktop sidebar, mobile header, and mobile overlay repeat brand and navigation behavior; use one navigation manifest and shared brand primitives.
2. Every screen needs the same `PageShell` and page-header composition.
3. Loading, empty, error, insufficient-data, processing, failed, and offline views must use shared route-state components.
4. Theme colors are duplicated in `THEME_COLORS`, `J_THEME_COLORS`, inline styles, and raw Tailwind arbitrary values; replace them with one typed theme registry backed by CSS variables.
5. Status pills use repeated raw color/opacity combinations; replace them with a typed `StatusBadge` variant map.
6. Repeated raw buttons should become shadcn `Button`/`IconButton` variants with one height, radius, focus ring, and disabled behavior.
7. Range selectors on Reflections, Journey, and Insights should share `DateRangeControl` while retaining feature-specific options.
8. Reflections and Journey both open evidence in a right drawer/full-screen mobile sheet; share the drawer shell and specialize the evidence row model through adapters.
9. Review and entry detail repeat approve/reject controls and mutation states; share `ApprovalActions`.
10. Entry, idea, memory, and evidence text blocks repeat date/source/content metadata; share editorial text and metadata primitives.
11. Journey chapter status, entry status, review state, and backfill state need non-color labels and a common status system.
12. Raw tables/charts need one accessible chart-frame pattern: visual, summary, optional disclosure, and TanStack-powered data table.
13. Mock data, data derivation, rendering, navigation, and mutations are co-located in one component; split them into fixtures, schemas, query functions, adapters/view models, feature components, and routes.
14. The prototype's `Screen` state and render switch must become App Router routes, layouts, and route-aware active navigation.

## Ambiguities and conflicts requiring product/design decisions

1. **Incomplete Make source:** `App.tsx` contains a literal truncation marker and references undefined screen/Journey components. Exact visual details for several screens cannot be verified from the export.
2. **No rendered preview verification:** no browser session was available, so source-derived behavior could not be compared with the live Make preview.
3. **Typography conflict:** older brief says Crimson Pro; current design system and theme say Lora. Font assets are not included.
4. **Sidebar conflict:** current design system specifies 264–296px; prototype uses 224px desktop/256px mobile; Reflections spec mentions 380–400px, which conflicts with both. Recommend the current design-system token.
5. **Missing required surfaces:** the Make brief calls for Insights and theme config/backfill, but the exported screen union/navigation does not contain them.
6. **Settings information architecture:** Profile exists, but it is unclear whether privacy/deletion and theme configuration are sections, tabs, or separate routes.
7. **New Entry navigation:** prototype makes New Entry a primary sidebar item; it may be better as the primary Entries action while retaining `/entries/new`. Confirm whether it remains in global navigation.
8. **Route vocabulary:** the design brief says conceptual navigation labels are approved but URL spellings were not frozen. Routes in this audit are proposals.
9. **Review naming:** internal type is `approvals`, visible label is `Review`. Use `Review` in UI and `/review` unless product says otherwise.
10. **Idea/memory filters:** default product behavior shows only approved items, but the prototype data contains pending/rejected states. Confirm which filters are exposed outside Review.
11. **Voice behavior:** requirements define limits and storage rules, but browser recording format support, permission-recovery copy, and retry behavior are not visually specified.
12. **Global error matrix:** the Make brief lists offline, 401, 404, 409, 413, 422, 429, 502, and 503 states, but exact user-facing copy and allowed recovery actions are not exported.
13. **Dark mode:** theme CSS includes fallback dark tokens despite explicit light-only scope. Remove/ignore them for v1 unless scope changes.
14. **Theme registry:** the prototype mixes a five-theme chart model and canonical eight-theme system. Production should use eight themes; confirm how legacy five-theme fixture data maps.
15. **Reflection derivation:** Reflections spec proposes a client-side adapter that may later call an LLM/backend. The production ownership and API contract are not frozen.
16. **Journey interpretation actions:** spec requires confirm, edit, or reject interpretations, but the visible exported source only proves selection/evidence behavior. Mutation contracts are missing.
17. **Prototype images:** the Make manifest exposes 14 unnamed PNG assets not referenced by the truncated source; their screen/state mapping is not available.

## Audit conclusion

The Make source establishes a strong visual system, shell, navigation vocabulary, and detailed Reflections/Journey direction. It does not constitute a complete production blueprint. The frontend should preserve its calm editorial character while replacing the monolith with route layouts, typed feature boundaries, shared states, a canonical token system, and contract-backed data adapters. Missing screens and conflicts above should be resolved before implementation reaches their feature slice.
