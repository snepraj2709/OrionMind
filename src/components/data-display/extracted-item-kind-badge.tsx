import {
  extractedItemKindPresentation,
  type ExtractedItemKind,
} from '@/config/status';

import { TaxonomyBadge, type TaxonomyBadgeTone } from './taxonomy-badge';

export interface ExtractedItemKindBadgeProps {
  kind: ExtractedItemKind;
  className?: string;
}

const kindTones: Record<ExtractedItemKind, TaxonomyBadgeTone> = {
  idea: 'primary',
  memory: 'accent',
  reflection: 'counterpoint',
};

export function ExtractedItemKindBadge({
  className,
  kind,
}: ExtractedItemKindBadgeProps) {
  return (
    <TaxonomyBadge
      className={className}
      label={extractedItemKindPresentation[kind].label}
      tone={kindTones[kind]}
    />
  );
}
