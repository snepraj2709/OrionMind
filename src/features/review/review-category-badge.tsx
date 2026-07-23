import {
  TaxonomyBadge,
  type TaxonomyBadgeTone,
} from '@/components/data-display';

import type { EntryInsightCategory, PatternCategory } from './model';

type ReviewCategory = EntryInsightCategory | PatternCategory;

export interface ReviewCategoryBadgeProps {
  category: ReviewCategory;
  className?: string;
}

const categoryPresentation = {
  energy: {
    label: 'Energy',
    tone: 'accent',
  },
  self_knowledge: {
    label: 'Self Knowledge',
    tone: 'primary',
  },
  needs_beliefs: {
    label: 'Needs & Beliefs',
    tone: 'counterpoint',
  },
  hidden_driver: {
    label: 'Hidden Driver',
    tone: 'primary',
  },
  recurring_loop: {
    label: 'Recurring Loop',
    tone: 'accent',
  },
  inner_tension: {
    label: 'Inner Tension',
    tone: 'counterpoint',
  },
} as const satisfies Record<
  ReviewCategory,
  { label: string; tone: TaxonomyBadgeTone }
>;

export function ReviewCategoryBadge({
  category,
  className,
}: ReviewCategoryBadgeProps) {
  const presentation = categoryPresentation[category];

  return (
    <TaxonomyBadge
      className={className}
      label={presentation.label}
      tone={presentation.tone}
    />
  );
}
