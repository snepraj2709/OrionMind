'use client';

import type { ColumnDef } from '@tanstack/react-table';
import {
  BookOpen,
  Check,
  ChevronRight,
  Home,
  Infinity,
  Lightbulb,
  MoreHorizontal,
  Sparkles,
  Zap,
} from 'lucide-react';
import { useState } from 'react';

import {
  ContentCard,
  EntryCard,
  InsightCard,
  ReflectionCard,
  StatCard,
  Surface,
} from '@/components/cards';
import {
  ConfidenceIndicator,
  DataTable,
  FilterBar,
  FilterField,
  PaginationControls,
  SortControl,
  type SortValue,
  StatusBadge,
  ThemeBadge,
} from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import {
  AppErrorBoundary,
  EmptyState,
  FullScreenState,
  InlineError,
  NoResultsState,
  PageErrorState,
  PageLoader,
  ProcessingState,
  SectionLoader,
  SkeletonList,
} from '@/components/feedback';
import {
  DateRangeField,
  type DateRangeValue,
  FormError,
  FormField,
  SearchInput,
  SelectField,
  SubmitButton,
  TextArea,
  TextInput,
} from '@/components/forms';
import {
  AppShell,
  AuthShell,
  BrandMark,
  ContentGrid,
  MobileNavigation,
  PageHeader,
  PageShell,
  PublicShell,
  Section,
  Sidebar,
} from '@/components/layout';
import {
  AppLink,
  Breadcrumbs,
  NavItem,
  SegmentedControl,
  Tabs,
} from '@/components/navigation';

interface CatalogRow {
  id: string;
  title: string;
  status: 'Ready' | 'Processing';
  theme: 'Career' | 'Health';
}

const catalogRows: CatalogRow[] = [
  { id: '1', title: 'A calmer work rhythm', status: 'Ready', theme: 'Career' },
  {
    id: '2',
    title: 'Morning walk notes',
    status: 'Processing',
    theme: 'Health',
  },
  { id: '3', title: 'Making room to pause', status: 'Ready', theme: 'Health' },
  {
    id: '4',
    title: 'A clearer weekly boundary',
    status: 'Ready',
    theme: 'Career',
  },
];

const catalogColumns: ColumnDef<CatalogRow>[] = [
  {
    accessorKey: 'title',
    header: 'Title',
  },
  {
    accessorKey: 'status',
    header: 'Status',
    cell: ({ row }) => (
      <StatusBadge
        label={row.original.status}
        variant={row.original.status === 'Ready' ? 'success' : 'processing'}
      />
    ),
  },
  {
    accessorKey: 'theme',
    header: 'Theme',
  },
];

function CatalogNavigation() {
  return (
    <div className="space-y-1">
      <NavItem
        href={{ pathname: '/dev/design-system' }}
        icon={<Home className="size-4" />}
        isActive
        label="Catalog"
      />
      <NavItem
        href={{ pathname: '/dev/design-system', hash: 'forms' }}
        icon={<BookOpen className="size-4" />}
        label="Forms"
      />
      <NavItem
        href={{ pathname: '/dev/design-system', hash: 'data' }}
        icon={<Sparkles className="size-4" />}
        label="Data display"
      />
    </div>
  );
}

export function DesignSystemCatalog() {
  const [segment, setSegment] = useState('week');
  const [strongSegment, setStrongSegment] = useState('all');
  const [reflectionSegment, setReflectionSegment] = useState('drivers');
  const [selectValue, setSelectValue] = useState('career');
  const [filterValue, setFilterValue] = useState('all');
  const [dateRange, setDateRange] = useState<DateRangeValue>({
    start: '2026-07-01',
    end: '2026-07-19',
  });
  const [sortValue, setSortValue] = useState<SortValue>({
    columnId: 'title',
    direction: 'asc',
  });
  const [catalogPage, setCatalogPage] = useState(0);

  const sidebar = (
    <Sidebar
      footer={<Typography variant="metadata">Development only</Typography>}
      header={<BrandMark />}
    >
      <CatalogNavigation />
    </Sidebar>
  );

  const mobileNavigation = (
    <MobileNavigation brand={<BrandMark />}>
      <CatalogNavigation />
    </MobileNavigation>
  );

  return (
    <AppShell mobileNavigation={mobileNavigation} sidebar={sidebar}>
      <PageShell className="space-y-16">
        <PageHeader
          actions={
            <AppButton
              leftIcon={<Check aria-hidden="true" className="size-4" />}
            >
              Primary action
            </AppButton>
          }
          breadcrumbs={
            <Breadcrumbs
              items={[
                {
                  label: 'Development',
                  href: { pathname: '/dev/design-system' },
                },
                { label: 'Design system' },
              ]}
            />
          }
          description="Reusable Orion components, interaction states, and responsive compositions. This route contains no product behavior."
          eyebrow="Development catalog"
          title="Orion component layer"
        />

        <Section
          description="All visual actions share one implementation and interaction contract."
          headingId="actions-heading"
          title="Actions"
        >
          <div className="flex flex-wrap items-center gap-4">
            <AppButton variant="primary">Primary</AppButton>
            <AppButton variant="secondary">Secondary</AppButton>
            <AppButton variant="ghost">Ghost</AppButton>
            <AppButton variant="destructive">Destructive</AppButton>
            <AppButton
              rightIcon={<ChevronRight aria-hidden="true" className="size-4" />}
              variant="link"
            >
              Link action
            </AppButton>
            <AppButton aria-label="More actions" variant="icon">
              <MoreHorizontal aria-hidden="true" className="size-4" />
            </AppButton>
            <AppButton loading loadingLabel="Saving changes">
              Save changes
            </AppButton>
            <AppButton disabled>Disabled</AppButton>
            <AppButton size="compact" variant="secondary">
              Compact
            </AppButton>
            <AppButton shape="pill" variant="secondary">
              Pill feedback action
            </AppButton>
          </div>
        </Section>

        <Section headingId="layout-heading" title="Layout shells">
          <ContentGrid columns="two">
            <Surface className="overflow-hidden p-0">
              <PublicShell className="p-4" contained>
                <Typography variant="body">PublicShell preview</Typography>
              </PublicShell>
            </Surface>
            <Surface className="overflow-hidden p-0">
              <AuthShell
                contained
                description="A focused authentication composition."
                footer={
                  <AppLink href={{ pathname: '/dev/design-system' }}>
                    Return to catalog
                  </AppLink>
                }
                title="AuthShell preview"
              >
                <TextInput
                  aria-label="Preview email"
                  placeholder="name@example.com"
                />
              </AuthShell>
            </Surface>
          </ContentGrid>
        </Section>

        <Section headingId="navigation-heading" title="Navigation">
          <div className="space-y-8">
            <div className="flex flex-wrap items-center gap-4">
              <AppLink href={{ pathname: '/dev/design-system' }}>
                App link
              </AppLink>
              <SegmentedControl
                ariaLabel="Date range"
                items={[
                  { value: 'week', label: 'Week' },
                  { value: 'month', label: 'Month' },
                  { value: 'year', label: 'Year' },
                ]}
                onValueChange={setSegment}
                value={segment}
              />
              <SegmentedControl
                ariaLabel="Strong date range"
                items={[
                  { value: 'week', label: 'Last 7 days' },
                  { value: 'month', label: 'Last 30 days' },
                  { value: 'all', label: 'All entries' },
                ]}
                onValueChange={setStrongSegment}
                value={strongSegment}
                variant="strong"
              />
            </div>
            <Tabs
              ariaLabel="Catalog tabs"
              defaultValue="overview"
              items={[
                {
                  value: 'overview',
                  label: 'Overview',
                  content: (
                    <Typography variant="body">Overview content</Typography>
                  ),
                },
                {
                  value: 'evidence',
                  label: 'Evidence',
                  content: (
                    <Typography variant="body">Evidence content</Typography>
                  ),
                },
                {
                  value: 'notes',
                  label: 'Notes',
                  content: (
                    <Typography variant="body">Notes content</Typography>
                  ),
                },
              ]}
            />
            <SegmentedControl
              ariaLabel="Icon segment example"
              items={[
                {
                  value: 'drivers',
                  label: 'Hidden drivers',
                  icon: <Lightbulb aria-hidden="true" className="size-4" />,
                },
                {
                  value: 'loops',
                  label: 'Recurring loops',
                  icon: <Infinity aria-hidden="true" className="size-4" />,
                },
                {
                  value: 'tensions',
                  label: 'Inner tensions',
                  icon: <Zap aria-hidden="true" className="size-4" />,
                },
              ]}
              onValueChange={setReflectionSegment}
              value={reflectionSegment}
            />
          </div>
        </Section>

        <Section headingId="cards-heading" title="Cards and surfaces">
          <ContentGrid columns="three">
            <Surface className="p-6">
              <Typography variant="body">Surface</Typography>
            </Surface>
            <ContentCard title="Content card">
              <Typography variant="body">Composable card content.</Typography>
            </ContentCard>
            <ReflectionCard
              statement="I am learning to leave more room between urgency and action."
              title="Reflection card"
            />
            <EntryCard
              excerpt="Today felt quieter after I protected the first hour of the morning."
              metadata="19 July · 8:42 AM"
              status={<StatusBadge label="Ready" variant="success" />}
              title="Entry card"
            />
            <InsightCard
              evidence="Observed across four entries."
              insight="Rest appears before your clearest decisions."
              title="Insight card"
            />
            <StatCard
              context="Across the current range"
              label="Journal entries"
              title="Stat card"
              value="24"
            />
          </ContentGrid>
        </Section>

        <Section headingId="feedback-heading" title="Feedback states">
          <div className="space-y-8">
            <AppErrorBoundary>
              <Surface className="p-4">
                <Typography variant="body">
                  AppErrorBoundary protecting healthy content.
                </Typography>
              </Surface>
            </AppErrorBoundary>
            <PageErrorState
              action={<AppButton variant="secondary">Retry</AppButton>}
              description="The reflection could not be loaded."
            />
            <InlineError>
              Check the highlighted fields and try again.
            </InlineError>
            <PageLoader contained label="Loading page content" />
            <SectionLoader />
            <SkeletonList count={2} />
            <EmptyState
              action={<AppButton>Write an entry</AppButton>}
              description="Begin with one honest sentence."
              title="Your journal is waiting"
            />
            <NoResultsState
              action={<AppButton variant="secondary">Clear filters</AppButton>}
            />
            <ProcessingState description="Your entry remains available while Orion finds themes." />
            <FullScreenState contained>
              <Typography variant="body">Contained FullScreenState</Typography>
            </FullScreenState>
          </div>
        </Section>

        <Section headingId="forms-heading" title="Forms">
          <div className="text-measure space-y-6" id="forms">
            <FormField
              description="Used only for account communication."
              id="catalog-name"
              label="Name"
            >
              <TextInput placeholder="Your name" />
            </FormField>
            <FormField id="catalog-reflection" label="Reflection">
              <TextArea placeholder="Write what feels true…" />
            </FormField>
            <SearchInput
              label="Search catalog"
              placeholder="Search components"
            />
            <SelectField
              id="catalog-theme"
              label="Theme"
              onValueChange={setSelectValue}
              options={[
                { value: 'career', label: 'Career' },
                { value: 'health', label: 'Health' },
              ]}
              value={selectValue}
            />
            <DateRangeField
              id="catalog-range"
              label="Date range"
              onChange={setDateRange}
              value={dateRange}
            />
            <FormError>
              The example form contains a recoverable error.
            </FormError>
            <SubmitButton loading={false}>Submit</SubmitButton>
          </div>
        </Section>

        <Section headingId="data-heading" title="Data display">
          <div className="space-y-10" id="data">
            <div className="flex flex-wrap gap-2">
              <StatusBadge label="Neutral" variant="neutral" />
              <StatusBadge label="Processing" variant="processing" />
              <StatusBadge label="Success" variant="success" />
              <StatusBadge label="Warning" variant="warning" />
              <StatusBadge label="Error" variant="error" />
            </div>
            <div className="flex flex-wrap gap-2">
              <ThemeBadge theme="career" />
              <ThemeBadge theme="money" />
              <ThemeBadge theme="health" />
              <ThemeBadge theme="loveLife" />
              <ThemeBadge theme="familyAndFriends" />
              <ThemeBadge theme="personalGrowth" />
              <ThemeBadge theme="funAndRecreation" />
              <ThemeBadge theme="homeAndLifestyle" />
            </div>
            <ConfidenceIndicator value={72} />
            <FilterBar>
              <FilterField
                id="catalog-filter"
                label="Status filter"
                onValueChange={setFilterValue}
                options={[
                  { value: 'all', label: 'All' },
                  { value: 'ready', label: 'Ready' },
                ]}
                value={filterValue}
              />
              <SortControl
                columns={[
                  { value: 'title', label: 'Title' },
                  { value: 'status', label: 'Status' },
                ]}
                onChange={setSortValue}
                value={sortValue}
              />
            </FilterBar>
            <PaginationControls
              canNextPage={catalogPage < 2}
              canPreviousPage={catalogPage > 0}
              onPageChange={setCatalogPage}
              onPageSizeChange={() => undefined}
              pageCount={3}
              pageIndex={catalogPage}
              pageSize={10}
            />
            <DataTable
              bulkActions={(rows) => (
                <AppButton size="compact">Archive {rows.length}</AppButton>
              )}
              caption="Catalog entry examples"
              columns={catalogColumns}
              data={catalogRows}
              enableBulkSelection
              filters={[
                {
                  columnId: 'status',
                  label: 'Status',
                  options: [
                    { value: 'Ready', label: 'Ready' },
                    { value: 'Processing', label: 'Processing' },
                  ],
                },
              ]}
              getRowId={(row) => row.id}
              pageSize={2}
              rowActions={(row) => (
                <AppButton
                  aria-label={`Actions for ${row.original.title}`}
                  size="compact"
                  variant="icon"
                >
                  <MoreHorizontal aria-hidden="true" className="size-4" />
                </AppButton>
              )}
              search={{ placeholder: 'Search entries…' }}
            />
          </div>
        </Section>

        <Section headingId="grid-heading" title="Content grid">
          <div className="space-y-8">
            <ContentGrid columns="two">
              <Surface className="p-6">
                <Typography variant="body">Grid column one</Typography>
              </Surface>
              <Surface className="p-6">
                <Typography variant="body">Grid column two</Typography>
              </Surface>
            </ContentGrid>
            <Surface className="p-6">
              <ContentGrid columns="reflectionSplit">
                <Typography variant="body">Reflection split 5</Typography>
                <Typography variant="body">Reflection split 4</Typography>
              </ContentGrid>
            </Surface>
            <Surface className="p-6">
              <ContentGrid columns="reflectionTriptych">
                <Typography className="p-4" variant="body">
                  Triptych 9
                </Typography>
                <Typography className="p-4" variant="body">
                  Triptych 11
                </Typography>
                <Typography className="p-4" variant="body">
                  Triptych 10
                </Typography>
              </ContentGrid>
            </Surface>
          </div>
        </Section>
      </PageShell>
    </AppShell>
  );
}
