import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  CircleX,
  Minus,
} from 'lucide-react';
import type { ReactNode } from 'react';

import { Badge } from '@/components/ui/badge';
import type { StatusTone } from '@/config/status';
import { cn } from '@/lib/utils';

export type StatusBadgeVariant = StatusTone;

export interface StatusBadgeProps {
  label: string;
  variant: StatusBadgeVariant;
  icon?: ReactNode;
  className?: string;
}

const statusClasses: Record<StatusBadgeVariant, string> = {
  neutral: 'border-border bg-muted text-foreground',
  processing:
    'border-status-processing/40 bg-status-processing/10 text-primary',
  success: 'border-status-success/40 bg-status-success/10 text-foreground',
  warning: 'border-status-warning/50 bg-status-warning/10 text-foreground',
  error: 'border-status-error/40 bg-status-error/10 text-destructive',
};

const statusIcons: Record<StatusBadgeVariant, ReactNode> = {
  neutral: <Minus aria-hidden="true" />,
  processing: <CircleDashed aria-hidden="true" className="animate-spin" />,
  success: <CheckCircle2 aria-hidden="true" />,
  warning: <AlertTriangle aria-hidden="true" />,
  error: <CircleX aria-hidden="true" />,
};

export function StatusBadge({
  className,
  icon,
  label,
  variant,
}: StatusBadgeProps) {
  return (
    <Badge
      className={cn(
        'type-metadata radius-pill border px-2 py-1',
        statusClasses[variant],
        className,
      )}
      variant={null}
    >
      {icon ?? statusIcons[variant]}
      {label}
    </Badge>
  );
}
