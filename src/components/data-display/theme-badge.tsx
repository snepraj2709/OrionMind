import type { CSSProperties } from 'react';

import { Badge } from '@/components/ui/badge';
import { themeRegistry, type ThemeKey } from '@/config/design-system';
import { cn } from '@/lib/utils';

export interface ThemeBadgeProps {
  theme: ThemeKey;
  className?: string;
}

type ThemeBadgeStyle = CSSProperties & {
  '--badge-theme-color': string;
};

export function ThemeBadge({ className, theme }: ThemeBadgeProps) {
  const config = themeRegistry[theme];
  const style: ThemeBadgeStyle = {
    '--badge-theme-color': config.color,
  };

  return (
    <Badge
      className={cn(
        'type-metadata theme-badge radius-pill border px-2 py-1',
        className,
      )}
      style={style}
      variant={null}
    >
      <span aria-hidden="true" className="theme-dot radius-pill size-2" />
      {config.label}
    </Badge>
  );
}
