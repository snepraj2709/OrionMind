# Orion design system

This document is the binding visual and implementation contract for Orion's frontend. Read it before every frontend task. Product screens must compose this system; they must not create page-local visual languages.

## Product principles

1. Calm over stimulating.
2. Content first.
3. Editorial rather than dashboard-like.
4. Establish hierarchy with typography, spacing, and borders.
5. Use minimal animation and decorative color.
6. Prefer consistency to page-specific styling.

Orion launches as a light-only experience. Ordinary cards are flat and border-led. Shadows are reserved for temporary overlay surfaces. Color supports meaning but is never the only status indicator.

## Font roles

Inter is the primary interface family. Use it for navigation, headings, buttons, labels, metadata, forms, tables, and general interface text.

Lora is the secondary editorial family. Use it only for journal excerpts, reflective statements, chapter titles, interpretations, long-form personal writing, and the shared Orion wordmark. The wordmark is the only approved italic use. Never use Lora for navigation, buttons, filters, labels, or metadata.

Only font weights 400, 500, and 600 are allowed. Both families are loaded centrally in the root layout through `next/font`.

## Typography roles

Every text element must use a semantic role through the `Typography` component or its matching `type-*` utility. Do not use Tailwind's numeric font-size utilities or arbitrary typography values.

| Role                      | Utility                          | Family | Size / line height | Weight | Additional rules                          |
| ------------------------- | -------------------------------- | ------ | ------------------ | ------ | ----------------------------------------- |
| Display                   | `type-display`                   | Inter  | 40 / 48px          | 600    | Reserved for rare top-level statements    |
| Page title                | `type-page-title`                | Inter  | 32 / 40px          | 600    | One route `h1`                            |
| Section title             | `type-section-title`             | Inter  | 24 / 32px          | 600    | Major page section                        |
| Component title           | `type-component-title`           | Inter  | 20 / 28px          | 600    | Card or composed component heading        |
| Reflection card statement | `type-reflection-card-statement` | Lora   | 24 / 30px          | 400    | Reflection cards; `-0.03em` tracking      |
| Journal excerpt           | `type-journal-excerpt`           | Lora   | 18 / 30px          | 400    | User-authored excerpt or chapter text     |
| Body large                | `type-body-large`                | Inter  | 18 / 28px          | 400    | Introductory interface copy               |
| Body                      | `type-body`                      | Inter  | 16 / 24px          | 400    | Default interface copy                    |
| Navigation                | `type-navigation`                | Inter  | 16 / 24px          | 500    | Navigation only                           |
| Button                    | `type-button`                    | Inter  | 15 / 20px          | 600    | Buttons and action labels                 |
| Body small                | `type-body-small`                | Inter  | 14 / 20px          | 400    | Supporting interface copy                 |
| Metadata                  | `type-metadata`                  | Inter  | 14 / 20px          | 500    | Dates, status context, and compact labels |
| Eyebrow                   | `type-eyebrow`                   | Inter  | 12 / 16px          | 600    | Uppercase with `0.08em` tracking          |
| Prominent brand wordmark  | `type-brand-wordmark-prominent`  | Lora   | 32 / 40px          | 400    | Italic; shared Orion brandmark only       |

Use the semantic `as` prop to preserve heading order independently of appearance:

```tsx
<Typography as="h1" variant="pageTitle">Entries</Typography>
<Typography as="p" variant="journalExcerpt">A journal excerpt…</Typography>
```

## Brand assets

`BrandMark` is the only application brand treatment. It renders `/images/light-mode-transparent.svg` at a constant 48×48px beside the constant Orion wordmark across public, authentication, desktop-sidebar, mobile-navigation, and development-catalog surfaces. The symbol is decorative because the visible wordmark supplies the link's accessible name. Do not recreate the mark with CSS shapes or page-specific sizing.

The dark-mode artwork is reserved for the application favicon. Ordinary textual references to Orion remain interface copy and do not use the brand asset.

## Color

Raw values live only in `src/styles/tokens.css`. Components use semantic Tailwind classes such as `bg-background`, `text-foreground`, and `border-border`, or a typed CSS-variable reference from `src/config/design-system.ts`.

### Semantic colors

| Token                | Value     | Purpose                           |
| -------------------- | --------- | --------------------------------- |
| Background           | `#f7f5ef` | Warm page canvas                  |
| Card                 | `#fcfbf7` | Contained surface                 |
| Secondary / muted    | `#ebe6da` | Quiet and selected surfaces       |
| Sidebar              | `#f1eee5` | Desktop navigation surface        |
| Input background     | `#ede8df` | Form-control fill                 |
| Foreground           | `#20212a` | Primary text                      |
| Muted foreground     | `#6f6b61` | Supporting text                   |
| Primary              | `#2A407A` | Primary action and loop structure |
| Primary foreground   | `#f7f5ef` | Content on primary                |
| Accent               | `#71917e` | Restrained accent and success cue |
| Counterpoint         | `#A9534C` | Opposing editorial concept        |
| Strong selection     | `#645846` | Opt-in emphasized range selection |
| Selection foreground | `#f7f5ef` | Content on a strong selection     |
| Border               | `#ddd8cc` | Default one-pixel border          |
| Destructive          | `#a9534d` | Destructive and error cue         |

Status aliases must use the semantic status tokens. Statuses always pair color with text, an icon, or another non-color cue.

### Life-theme colors

The canonical theme registry is typed and contains exactly eight themes:

| Theme              | Value     |
| ------------------ | --------- |
| Career             | `#8B7085` |
| Money              | `#B28D48` |
| Health             | `#71917E` |
| Love Life          | `#C78488` |
| Family and Friends | `#7086A7` |
| Personal Growth    | `#C47D67` |
| Fun and Recreation | `#9A83A5` |
| Home and Lifestyle | `#8D877B` |

Feature code receives a `ThemeKey` and resolves it through `themeRegistry`. It must never accept or render an API-provided color string.

## Spacing

The approved 8px-based scale is 4, 8, 12, 16, 24, 32, 40, 48, 64, and 80px. In Tailwind these map to `1`, `2`, `3`, `4`, `6`, `8`, `10`, `12`, `16`, and `20` respectively. The Tailwind spacing namespace is restricted to these stops.

Use spacing to group related content before adding more surface treatment. Do not use bracket notation, raw pixel spacing, or unapproved scale steps.

## Borders, radii, and elevation

| Role                                | Value | Utility              |
| ----------------------------------- | ----- | -------------------- |
| Small control                       | 8px   | `radius-control`     |
| Button / input                      | 10px  | `radius-interactive` |
| Card                                | 14px  | `radius-card`        |
| Large surface                       | 16px  | `radius-surface`     |
| Badge / chip / approved pill action | 999px | `radius-pill`        |

Use a one-pixel `border-border` border by default. Do not use shadows on ordinary cards. `--shadow-overlay` is reserved for sheets, drawers, dialogs, and other temporary elevated surfaces. `--shadow-selected-control` is the only approved control elevation and identifies the selected item in the shared prominent `SegmentedControl`.

Pill-shaped actions are an explicit `AppButton` shape variant for compact feedback choices. They keep the shared button typography, focus state, and 44px minimum touch target. Do not reproduce this treatment with page-local radius classes.

Outline actions remain part of the same `AppButton` implementation. `outline` is the neutral bordered treatment used by pagination, `accentOutline` is the affirmative editorial action, and `rejectOutline` stays neutral until pointer hover reveals destructive text and border color. Destructive meaning must still be present in the action label or icon so hover color is not the only cue.

## Layout

Every route uses `PageShell` or an approved layout shell that contains it. `PageShell` is full width, centered at a maximum of 1440px, and applies:

```css
padding-inline: clamp(20px, 3.5vw, 56px);
padding-block: clamp(28px, 4vw, 56px);
```

Do not constrain an entire page with `max-w-xl`, `max-w-3xl`, or a similar reading-width utility. Constrain only the text inside a full-width composition:

- `text-measure`: 68ch for default readable copy.
- `text-measure-wide`: 80ch for journal entries and other long personal writing.

The desktop sidebar uses `clamp(264px, 18vw, 296px)` and collapses below 1024px. Use the typed `responsiveLayoutVariants.desktopSidebar` and `responsiveLayoutVariants.collapsedNavigation` classes to keep both presentations on opposite sides of the same `sidebar` breakpoint. Desktop and collapsed navigation must share one future navigation manifest; a page never owns sidebar state or navigation data.

Reflection compositions may use the shared `ContentGrid` variants:

- `reflectionSplit`: 5:4 columns with one internal separator.
- `reflectionTriptych`: 9:11:10 columns with separators between regions.

Both variants collapse to one column below the 1024px sidebar breakpoint. The separator changes from vertical to horizontal when stacked.

The brown strong-selection treatment is opt-in through `SegmentedControl variant="strong"`. All segmented controls use the shared prominent composition: a 48px control inside an 8px inset, 16px outer radius, 14px selected-item radius, navigation typography, muted inactive labels, and the approved selected-control elevation. Items may include a decorative 24px icon centered in a 40px padded icon slot beside their required label. Below 640px, icon-bearing items visually hide their labels while preserving the accessible name; text-only filters keep their labels. The control owns horizontal scrolling so it never creates page overflow.

## Responsive and accessibility rules

- The layout must work without horizontal page scrolling at 320px.
- The sidebar collapses below 1024px.
- Controls may reflow or approved inner regions may scroll, but functionality cannot disappear.
- Every interactive target is keyboard accessible and has a visible focus state.
- Prefer native elements. Preserve one `h1` and a logical heading order per route.
- Dynamic status changes use a polite live region.
- Charts require a textual summary and accessible data-table alternative.
- Respect reduced-motion preferences. Animation must be brief, functional, and non-essential.

## Components and ownership

- `src/components/ui`: unmodified shadcn behavior primitives.
- `src/components/design-system`: Orion variants and visual semantics, including typography.
- `src/components/layout`: application and page shells, including `PageShell`.
- `src/components/shared`: reusable product compositions.
- `src/components/feedback`: shared status, alert, and recovery behavior.
- `src/components/data-display`: shared editorial and structured-data presentation.
- `src/features/<feature>`: feature-owned behavior exposed through that feature's root `index.ts` only.

Search these locations before creating a component. Do not change a shadcn primitive for feature-specific behavior; add a design-system or shared wrapper instead. Features may import another feature only through its public root export, never through internal paths.

## Search and collection controls

`SearchControl` is the canonical search composition. It combines a labeled search field, decorative search icon, primary Search action, and optional filter/action slots. Typing changes only its internal draft; Search or Enter commits the text through `onSearch`. Dropdown filters and segmented controls remain immediate. Do not add keyboard-shortcut decoration to the field.

When a compact filter row uses the selected value as its visible copy, `FilterField hideLabel` may visually hide the field label while preserving it for assistive technology. Do not remove the accessible label or replace it with placeholder-only naming.

`PaginationControls` always renders outlined Prev and Next actions around `Page X of Y` metadata. First/last actions and user-facing page-size selectors are not part of Orion's pagination language. Consumers keep a fixed page size in their data/query boundary.

The Review queue uses a feature-owned editorial row instead of a card: one full Lora statement, accent-outline Approve, neutral-to-destructive-hover Reject, and a semantic horizontal separator after every row. The row has no surface background, border, radius, shadow, title, date, or status badge. This treatment is specific to Review; richer extracted-item cards remain valid in Entry Detail and saved collections.

## Required view states

Every data view handles loading, error, empty, and success. Where applicable, it also handles processing, failure, insufficient data, offline, and retry states. Shared state components must preserve the page heading and approximate final layout to prevent disruptive replacement.

## Enforcement

`npm run check:design-system` performs repository checks for:

- raw hexadecimal colors outside `src/styles/tokens.css`;
- arbitrary design-related Tailwind values and non-semantic font-size classes;
- raw CSS typography declarations outside the typography contract;
- duplicate React component declaration names;
- feature imports that bypass another feature's public boundary.

The check runs as part of `npm run lint`. Typecheck, lint, tests, and the production build are mandatory before handoff.

If a deliberate exception is unavoidable, add it to `docs/design-exceptions.md` before implementation with its owner, scope, reason, and removal or review condition.
