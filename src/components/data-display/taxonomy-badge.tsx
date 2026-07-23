import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

export type TaxonomyBadgeTone = 'primary' | 'accent' | 'counterpoint';

export interface TaxonomyBadgeProps {
  label: string;
  tone: TaxonomyBadgeTone;
  className?: string;
}

const toneClasses: Record<TaxonomyBadgeTone, string> = {
  primary: 'border-primary/30 bg-primary/10',
  accent: 'border-accent/40 bg-accent/10',
  counterpoint: 'border-counterpoint/30 bg-counterpoint/10',
};

export function TaxonomyBadge({ className, label, tone }: TaxonomyBadgeProps) {
  return (
    <Badge
      className={cn(
        'type-tag radius-pill text-foreground border px-2 py-1',
        toneClasses[tone],
        className,
      )}
      variant={null}
    >
      {label}
    </Badge>
  );
}
