# Orion Figma deviations

This file records known differences between the Figma Make reference and the production frontend. Each difference is reviewed against the approved Orion design system before implementation.

## Application shell

- **Protected screenshots unavailable:** The Make integration exposes the application-shell source, but the protected screen component bodies and screenshots are absent from the exported bundle. The bundled PNG assets contain repeated authentication captures and blank frames. The in-app browser connection is also unavailable in this session. Shell comparison is therefore source-based until a protected Make preview can be captured.
- **Sidebar width:** The Make prototype hardcodes a 224px desktop sidebar. Production uses the approved `clamp(264px, 18vw, 296px)` design-system token.
- **Brand asset:** The supplied transparent `light-mode-transparent.svg` replaces the prototype's generated dots while retaining the shared Lora wordmark. One shared `BrandMark` is used across public, authentication, desktop-sidebar, and mobile-navigation surfaces.
- **Mobile navigation:** The prototype uses a hand-built overlay. Production uses the shared accessible sheet with focus management, escape-key dismissal, and the same navigation manifest as desktop.

## Entries

- **Screen reference unavailable:** `App.tsx` supplies the five entry fixtures and route transition, but the `EntriesScreen` component body and protected screenshots are absent from the Make export. The production list follows the approved editorial list pattern and uses the source fixture content.
- **Screenshot hierarchy:** The later Entries screenshot is used for its compact header, short dates, flat divided rows, two-line excerpts, and full-row navigation. The preview notice and question-mark control belong to the design tool and are intentionally omitted.
- **Filters and pagination:** Production retains subdued text and status filters plus pagination because they are established application behavior. Page sizes use the shared 10, 20, and 50 configuration across collection screens; selected options use the semantic beige `secondary` surface instead of the green accent shown by the prototype control.
- **Accessible theme labels:** The screenshot represents themes as color-only dots. Production keeps compact labeled `ThemeBadge` components so color is never the only identifier.
- **Approved shell and typography:** The shared sidebar, authenticated identity, Inter interface roles, Lora journal-excerpt role, and canonical image-based brandmark remain unchanged rather than copying the screenshot's page-specific shell and wordmark treatment.
- **Theme vocabulary:** The prototype's Growth, Creativity, Connection, Health, and Work labels are mapped to the approved eight-theme registry rather than retaining a second page-specific palette.
- **Route behavior:** The prototype uses local screen state. Production entry rows use stable `/entries/[entryId]` URLs and preserve the processing and failed states from the source data.

## New Entry

- **Screen reference unavailable:** The Make source invokes `NewEntryScreen`, but its component definition and route screenshots are missing from the exported source manifest. Layout and state behavior therefore follow the journaling requirements, the approved page/form patterns, and the source's text/voice navigation contract.
- **Unsaved-content warning:** Production uses the browser's native confirmation UI for protected in-app links and `beforeunload` protection for refresh, tab close, and external navigation. The Make implementation for this behavior is unavailable.
- **Voice privacy and limit:** The recorder states the source requirement's 20-minute limit and that audio is deleted after transcription. The typed mock repository stores only a processing entry placeholder, never the audio blob.

## Entry Detail

- **Screen reference unavailable:** `App.tsx` routes a selected fixture into `EntryDetailScreen`, but that component body and protected screenshots are absent from the Make export. The production view uses the source-backed entry, theme, idea, memory, approval, processing, and failed data while following Orion's approved editorial detail pattern.
- **URL and not-found behavior:** The Make prototype holds the selected entry in local state. Production uses `/entries/[entryId]`, supports direct links, and renders an explicit not-found state for unknown identifiers.
- **Refresh and offline behavior:** The production view adds non-destructive background refresh, retry, and offline-safe decision controls required by the frontend architecture. Those states are not inspectable in the exported Make source.

## Review

- **Screen reference unavailable:** The Make source verifies a combined queue of pending ideas and memories, its count, and approve/reject transitions, but the `ApprovalsScreen` body and screenshots are absent from the export. Production composes the same `ReviewItemCard` and `ApprovalActions` used by Entry Detail.
- **Filter semantics:** Production provides kind and text filters with a distinct no-results state, pagination, background refresh, and an empty caught-up state. The exported Make source does not expose its detailed filter layout.
- **Route spelling:** The source navigation label is `Review` while the prototype state is named `approvals`. Production keeps the approved `/approvals` route and presents `Review` consistently in navigation and the page heading.

## Ideas and Memories

- **Screen references unavailable:** The Make source passes the full entry collection to `IdeasScreen` and `MemoriesScreen`, but neither component body nor protected screenshot is present in the export. Production uses the approved saved-item list pattern and the source-backed idea/memory content hierarchy.
- **Shared composition:** Both routes use one typed `SavedItemsScreen` rather than duplicating search, pagination, card, status, loading, empty, error, offline, or refresh logic. Route-specific copy and item kind remain in the feature folders.
- **Saved fixtures:** The exported Make data contains only one already-approved memory and no approved idea. Production adds clearly local, replaceable approved fixtures so both populated routes can be visually reviewed; these fixtures are not treated as an API contract.

## Reflections

- **Reference images:** The implemented tab hierarchies follow `images/Reflection-Hidden-driver-final.png`, `images/reflection-reccuring-loop.png`, and `images/Reflection-inner-tension.png`.
- **Typography adaptation:** Page and section headings remain Inter. Screenshot serif headings are not copied; Lora is limited to the approved 24/30 reflection statement, interpretations, and long-form reflective copy.
- **Color adaptation:** Lavender loop decoration is replaced by global primary `#2A407A`. Inner-tension sides use primary plus the non-error counterpoint token. The brown active range is an opt-in strong-selection treatment.
- **Card adaptation:** Each tab uses flat, border-led Orion `Surface` compositions. Recurring Loops is one surface with internal separators; Inner Tensions removes nested integration cards.
- **Responsive adaptation:** The screenshot-specific 5:4 and 9:11:10 structures collapse below 1024px. Inner Tensions changes from a horizontal comparison to a vertical comparison at the same breakpoint so the route remains usable without horizontal overflow at 320px.

- **Written specification only:** The Make export includes two identical Reflections redesign briefs but no rendered protected-screen component or screenshot. Production follows that written hierarchy and copy, and its desktop/mobile captures are therefore validated against the brief rather than a pixel reference.
- **Approved shell width:** The brief asks to preserve a 380–400px sidebar. Production retains the approved Orion shell token, `clamp(264px, 18vw, 296px)`, so Reflections does not introduce a route-specific layout exception.
- **Semantic color limits:** The brief mentions restrained lavender and terracotta accents. Those colors do not have approved semantic roles in the Orion design system, so the implementation uses the existing `accent`, `primary`, `muted`, and border tokens and never treats color as the only status cue.
- **Refresh and filtered-empty states:** A compact refresh control, preserved-data refresh failure, offline notice, and distinct no-results state are included to satisfy the application data-state contract. They extend the brief without changing its Hidden Drivers, Recurring Loops, and Inner Tensions hierarchy.
- **API boundary:** Production Reflections requests one strict, Zod-validated aggregate from authenticated `GET /api/v1/reflections?range=7d|30d|all`. Ownership comes from the bearer token, tabs remain local UI state, and backend snapshot storage supplies the three reflection sections.
- **Review integration limitation:** Approved Review reflections remain separate from longitudinal reflection snapshots. The aggregate endpoint reads accepted entry analyses and signals rather than the mock Review store.

### Evidence and typography

- **Reference basis:** The Make bundle includes two identical `reflections-redesign` specifications even though the protected component body and screenshots are missing. Production follows the later approved three-tab direction, including the date-range control, hidden drivers, recurring loop, inner tensions, evidence separation, and feedback controls. The focus experiment was removed by product decision.
- **Typography:** An older Figma description names Crimson for reflective prose. Production uses Lora through the approved `type-reflection-card-statement` semantic utility and the `reflectiveStatement` component variant.
- **Evidence language:** Production consistently separates original journal wording from Orion interpretations in the shared evidence drawer. This is more explicit than the inspectable prototype source, but is required by the bundled trust guidance.

## Journey

- **Pre-unlock reference:** `images/Journey-screen-before-unlock.png` defines the locked hierarchy, progress requirements, two-panel graph comparison, and exact copy. The screenshot's question-mark control is design-tool chrome and is omitted.
- **Shared-shell adaptation:** Production retains the canonical Orion brandmark, current route manifest, approved sidebar width, and authenticated user treatment. The screenshot-era Ideas and Memories links are not restored.
- **Control and color adaptation:** The six-option range selector uses the shared compact `SegmentedControl` density with the approved strong brown selection. Screenshot lavender is replaced by semantic primary; entry progress uses accent. The sample caption remains approved non-italic interface copy.
- **Locked steamgraph:** The personal placeholder and sample preview share one smooth, accessible SVG steamgraph backed by typed endpoint fixtures. Theme colors resolve through the canonical registry, and a screen-reader data table supplies the chart alternative.
- **Unlock boundary:** The simulated status endpoint controls whether the locked reference or the existing full Journey renders. Progress values are descriptive and never override the server-provided `enabled` state.
- **Conflicting specifications:** `journey-screen.md` describes a graph-left/vertical-rail layout, while the later `journey-redesign-spec.md` and the accessible portion of `App.tsx` describe a full-width river, horizontal chapter rail, and four detail tabs. Production follows the later redesign.
- **Chart implementation:** Production renders the eight-theme river as accessible SVG with an accompanying data table. No chart dependency was added because the existing approved architecture does not require one and the SVG preserves the specified interaction and responsive horizontal overflow.
- **Boundary confidence:** Chapter regions and boundary explanations are deterministic typed mock interpretations until a longitudinal backend exists. They are visibly tentative and always link back to source evidence.

## Profile

- **Information architecture:** The audit proposed `/settings/profile`, while the approved routing task later fixed the protected route as `/profile`. Production follows `/profile` and keeps privacy, deletion, theme configuration, and backfill outside this screen until their route structure is approved.
- **Screen reference unavailable:** The Make export does not include an inspectable Profile component. Production implements the documented profile states—loading, dirty, submitting, saved, validation error, API error, offline, and signed out—using the shared form and feedback components.
- **Mock persistence:** Profile updates use a typed replaceable repository. Email remains read-only because it belongs to the authentication provider; Supabase replacement can occur behind the repository and AuthProvider boundaries.

## Comparison limitations

- The exported `App.tsx` contains a literal truncation marker inside the source, and embedded Make images are incomplete. Figma Make does not provide node screenshots for this file type in the available integration.
- No signed-in interactive browser instance was available during this pass. Desktop and mobile production screenshots can therefore verify responsive behavior and internal consistency, but a pixel-diff against protected Figma captures remains pending until complete source captures are available.
