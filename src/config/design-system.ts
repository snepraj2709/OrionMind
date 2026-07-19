export const typographyVariants = {
  display: 'type-display',
  pageTitle: 'type-page-title',
  sectionTitle: 'type-section-title',
  componentTitle: 'type-component-title',
  reflectiveStatement: 'type-reflection-card-statement',
  journalExcerpt: 'type-journal-excerpt',
  bodyLarge: 'type-body-large',
  body: 'type-body',
  navigation: 'type-navigation',
  button: 'type-button',
  bodySmall: 'type-body-small',
  metadata: 'type-metadata',
  eyebrow: 'type-eyebrow',
} as const;

export type TypographyVariant = keyof typeof typographyVariants;

export const themeRegistry = {
  career: { label: 'Career', color: 'var(--theme-career)' },
  money: { label: 'Money', color: 'var(--theme-money)' },
  health: { label: 'Health', color: 'var(--theme-health)' },
  loveLife: { label: 'Love Life', color: 'var(--theme-love-life)' },
  familyAndFriends: {
    label: 'Family and Friends',
    color: 'var(--theme-family-friends)',
  },
  personalGrowth: {
    label: 'Personal Growth',
    color: 'var(--theme-personal-growth)',
  },
  funAndRecreation: {
    label: 'Fun and Recreation',
    color: 'var(--theme-fun-recreation)',
  },
  homeAndLifestyle: {
    label: 'Home and Lifestyle',
    color: 'var(--theme-home-lifestyle)',
  },
} as const;

export type ThemeKey = keyof typeof themeRegistry;

export const spacingScale = {
  1: 'var(--space-1)',
  2: 'var(--space-2)',
  3: 'var(--space-3)',
  4: 'var(--space-4)',
  6: 'var(--space-6)',
  8: 'var(--space-8)',
  10: 'var(--space-10)',
  12: 'var(--space-12)',
  16: 'var(--space-16)',
  20: 'var(--space-20)',
} as const;

export const radiusVariants = {
  control: 'radius-control',
  interactive: 'radius-interactive',
  card: 'radius-card',
  surface: 'radius-surface',
  pill: 'radius-pill',
} as const;

export const layoutTokens = {
  contentMax: 'var(--content-max)',
  sidebarWidth: 'var(--sidebar-width)',
  sidebarCollapseBreakpoint: 'var(--sidebar-collapse-breakpoint)',
  textMeasure: 'var(--text-measure-default)',
  wideTextMeasure: 'var(--text-measure-wide)',
} as const;

export const responsiveLayoutVariants = {
  desktopSidebar: 'sidebar-width hidden sidebar:flex',
  collapsedNavigation: 'flex sidebar:hidden',
} as const;
