import { Badge } from '@/components/ui/badge';
import {
  extractedItemKindPresentation,
  type ExtractedItemKind,
} from '@/config/status';
import { cn } from '@/lib/utils';

export interface ExtractedItemKindBadgeProps {
  kind: ExtractedItemKind;
  className?: string;
}

const kindClasses: Record<ExtractedItemKind, string> = {
  idea: 'border-primary/30 bg-primary/10',
  memory: 'border-accent/40 bg-accent/10',
  reflection: 'border-counterpoint/30 bg-counterpoint/10',
};

export function ExtractedItemKindBadge({
  className,
  kind,
}: ExtractedItemKindBadgeProps) {
  return (
    <Badge
      className={cn(
        'type-tag radius-pill text-foreground border px-2 py-1',
        kindClasses[kind],
        className,
      )}
      variant={null}
    >
      {extractedItemKindPresentation[kind].label}
    </Badge>
  );
}
