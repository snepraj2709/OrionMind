# Orion component catalog

This catalog documents Orion's reusable frontend layer. Read `docs/design-system.md` first. Product routes compose these components and never import `src/components/ui` directly.

The interactive catalog is available at `/dev/design-system`. It demonstrates every component family, all feedback states, button and badge variants, responsive shell behavior, form controls, and the generic data table without implementing product behavior.

## Ownership and imports

| Layer             | Import                       | Responsibility                                                              |
| ----------------- | ---------------------------- | --------------------------------------------------------------------------- |
| Design system     | `@/components/design-system` | Typography and the shared action implementation                             |
| Layout            | `@/components/layout`        | Application, public, auth, page, section, sidebar, and grid composition     |
| Navigation        | `@/components/navigation`    | Links, navigation rows, breadcrumbs, tabs, and segmented controls           |
| Cards             | `@/components/cards`         | Flat surfaces and named editorial card compositions                         |
| Feedback          | `@/components/feedback`      | Error boundaries, loading, empty, error, processing, and full-screen states |
| Forms             | `@/components/forms`         | Labeled controls, form errors, date ranges, search, and submit behavior     |
| Data display      | `@/components/data-display`  | Typed tables, filters, sorting, pagination, status, theme, and confidence   |
| shadcn primitives | `@/components/ui/*`          | Internal behavior primitives; wrapper implementation only                   |

Route and feature code must use the public wrapper imports. The automated design-system check rejects direct shadcn imports from `src/app` and `src/features`.

## Layout

### Application shells

- `AppShell` composes the desktop sidebar, collapsed mobile navigation, skip link, and main landmark. Authentication and data fetching stay in route layouts.
- `PublicShell` provides a centered, full-height `PageShell` for public content.
- `AuthShell` specializes `PublicShell` with a constrained auth composition, title, description, brand, and footer.
- `Sidebar` owns desktop width and below-1024px visibility. Supply shared navigation data as children.
- `MobileNavigation` uses the shadcn sheet behavior and must receive the same navigation items as `Sidebar`.

```tsx
<AppShell
  sidebar={<Sidebar>{navigation}</Sidebar>}
  mobileNavigation={
    <MobileNavigation brand={<Brand />}>{navigation}</MobileNavigation>
  }
>
  <PageShell>{children}</PageShell>
</AppShell>
```

### Page composition

- `PageShell` is mandatory for route content. Do not add another page-level maximum width.
- `PageHeader` renders the route `h1`, optional eyebrow, description, breadcrumbs, and actions.
- `Section` renders an optional `h2`, description, actions, and content spacing. Supply a stable `headingId` when a title is present.
- `ContentGrid` supports `one`, `two`, `three`, `editorial`, `reflectionSplit`, and `reflectionTriptych` responsive arrangements. The reflection grids own their approved internal separators and collapse at the sidebar breakpoint.

## Actions

`AppButton` is the only Orion action implementation. It wraps the shadcn button primitive and supports:

- variants: `primary`, `secondary`, `ghost`, `destructive`, `link`, and `icon`;
- sizes: `default` (44px) and `compact` (36px visual height with a 44px hit area);
- shapes: `default` (10px) and `pill` (feedback actions only);
- `loading`, `loadingLabel`, `leftIcon`, `rightIcon`, disabled state, and `asChild`;
- one consistent focus ring, with either the default 10px radius or approved pill shape.

An icon-only button must have an `aria-label`; the component rejects an unlabeled icon variant.

```tsx
<AppButton leftIcon={<Plus aria-hidden="true" />} loading={isPending}>
  Add entry
</AppButton>

<AppButton aria-label="Entry actions" variant="icon">
  <MoreHorizontal aria-hidden="true" />
</AppButton>
```

## Navigation

- `AppLink` supplies the shared focus state, touch target, and `aria-current` behavior.
- `NavItem` adds label, icon, optional badge, and active styling to `AppLink`.
- `Breadcrumbs` accepts ordered `{ label, href? }` items; the final item is the current page.
- `Tabs` accepts typed items with `value`, `label`, `content`, and optional disabled state. Radix provides arrow-key navigation and tab/panel semantics.
- `SegmentedControl` is the shared single-value switch used by New Entry, Reflections, filters, and display ranges. Items accept an optional decorative icon alongside their required visible label. Its opt-in `strong` variant uses the strong-selection tokens; `default` remains unchanged. It is not a substitute for route navigation.

## Cards and surfaces

`Surface` is the base flat card and supports `default`, `muted`, `interactive`, and `overlay` variants. Ordinary surfaces do not have shadows. Only `overlay` uses the approved overlay elevation.

Named compositions all build on `Surface` and shadcn card slots:

- `ContentCard`: title, description, actions, content, and optional footer.
- `ReflectionCard`: a tighter Lora statement at 24/30px, weight 400, and `-0.03em` tracking, with optional supporting text.
- `EntryCard`: journal excerpt, metadata, and status.
- `InsightCard`: interface insight and supporting evidence.
- `StatCard`: value, label, and optional context.

Do not place a bordered card inside another bordered card. Use spacing, a separator, or an unbordered content region inside the parent surface.

## Feedback and state handling

Every data view explicitly maps loading, error, empty, and success states before rendering success content.

| Component          | Use                                                                         |
| ------------------ | --------------------------------------------------------------------------- |
| `AppErrorBoundary` | Unexpected client-render failures; use route `error.tsx` for route failures |
| `PageErrorState`   | Recoverable page or large-region failure                                    |
| `InlineError`      | Compact contextual error beside affected content                            |
| `PageLoader`       | Initial route-sized loading status                                          |
| `SectionLoader`    | A bounded region loading independently                                      |
| `SkeletonList`     | Editorial list-shaped loading layout                                        |
| `EmptyState`       | Successful query with no records                                            |
| `NoResultsState`   | Records exist but current filters match none                                |
| `ProcessingState`  | A visible entity is still being processed                                   |
| `FullScreenState`  | Centered full-viewport or contained state composition                       |

Actions are passed as `ReactNode` so callers expose only recovery actions supported by the product/API contract.

## Forms

- `FormField` owns the label, description, error association, required cue, and `aria-describedby` wiring. It accepts a control element or a render function for compound controls.
- `TextInput` and `TextArea` apply the Orion input surface, typography, radius, focus, disabled, and invalid states.
- `SearchInput` adds a decorative search icon and an explicit accessible label.
- `SelectField` wraps the shadcn select and `FormField` association.
- `DateRangeField` renders a labeled start/end fieldset and constrains the dates against each other.
- `FormError` is the form-level accessible error region.
- `SubmitButton` is `AppButton` with `type="submit"`; use its loading state during submission.

React Hook Form owns form state. Register native controls normally and map schema/API messages to `FormField.error` or `FormError`.

## Data display

### Status, theme, and confidence

- `StatusBadge` variants are `neutral`, `processing`, `success`, `warning`, and `error`. Each includes an icon and text so color is not the only cue.
- `ThemeBadge` accepts only the typed canonical `ThemeKey`; API-provided color strings are not accepted.
- `ConfidenceIndicator` exposes a progressbar value plus a Low, Moderate, or High text label.

### Table controls

- `FilterBar` composes filter fields and optional actions.
- `FilterField` is the table-oriented select wrapper.
- `SortControl` provides column and direction selection where header sorting is not suitable.
- `PaginationControls` provides first, previous, next, last, page count, and page-size controls.

### Generic data table

`DataTable<TData, TValue>` uses TanStack Table and requires typed column definitions, data, and an accessible caption.

```tsx
const columns: ColumnDef<Entry>[] = [
  { accessorKey: 'title', header: 'Title' },
  { accessorKey: 'status', header: 'Status' },
];

<DataTable
  caption="Journal entries"
  columns={columns}
  data={entries}
  getRowId={(entry) => entry.id}
  search={{ label: 'Search entries' }}
  filters={statusFilters}
  rowActions={(row) => <EntryActions entry={row.original} />}
/>;
```

Supported behavior:

- client-side sorting through sortable headers;
- global text search and exact column filters;
- pagination and page-size selection;
- optional toolbar content and row actions;
- optional bulk selection and selected-row actions;
- loading, safe error, empty-data, and filtered-no-results states;
- semantic desktop table and responsive mobile card list;
- optional `renderMobileRow` for a domain-specific mobile reading order.

For server-side datasets, adapt pagination/filter callbacks at the feature boundary rather than pretending a partial page is the entire client-side dataset.

## Accessibility checklist

- Use visible text for status meaning; icons are supplemental.
- Give every icon-only action an `aria-label`.
- Keep one route `h1` and preserve heading order independently of visual typography.
- Never remove the shared focus ring.
- Keep desktop and mobile navigation sourced from the same item model.
- Supply an accessible table caption and meaningful mobile row order.
- Preserve native labels, fieldsets, buttons, links, and tab semantics.
- Functional animation must remain understandable when reduced-motion styles collapse its duration.
