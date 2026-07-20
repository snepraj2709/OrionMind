'use client';

import type { ReactNode } from 'react';

import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { cn } from '@/lib/utils';

export interface SegmentedControlItem {
  value: string;
  label: string;
  icon?: ReactNode;
  disabled?: boolean;
}

export interface SegmentedControlProps {
  items: SegmentedControlItem[];
  ariaLabel: string;
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  className?: string;
  variant?: 'default' | 'strong';
  density?: 'prominent' | 'compact';
}

const itemVariantClasses = {
  default:
    'data-[state=on]:bg-card data-[state=on]:text-foreground data-[state=on]:shadow-selected-control',
  strong:
    'data-[state=on]:bg-selection-strong data-[state=on]:text-selection-strong-foreground data-[state=on]:shadow-selected-control',
} as const;

const densityClasses = {
  prominent: {
    group: 'radius-surface gap-1 p-1',
    item: 'control-prominent radius-card px-4',
  },
  compact: {
    group: 'radius-interactive gap-0 p-0',
    item: 'control-default radius-control border-r border-border px-3 last:border-r-0',
  },
} as const;

export function SegmentedControl({
  ariaLabel,
  className,
  defaultValue,
  density = 'prominent',
  items,
  onValueChange,
  value,
  variant = 'default',
}: SegmentedControlProps) {
  return (
    <ToggleGroup
      aria-label={ariaLabel}
      className={cn(
        'border-border bg-muted max-w-full overflow-x-auto border',
        densityClasses[density].group,
        className,
      )}
      defaultValue={defaultValue}
      onValueChange={(nextValue) => {
        if (nextValue) onValueChange?.(nextValue);
      }}
      type="single"
      value={value}
      spacing={1}
    >
      {items.map((item) => (
        <ToggleGroupItem
          className={cn(
            'type-navigation text-muted-foreground hover:bg-card/60 hover:text-foreground gap-0',
            densityClasses[density].item,
            itemVariantClasses[variant],
            density === 'compact' &&
              'data-[state=on]:first:radius-interactive data-[state=on]:last:radius-interactive data-[state=on]:shadow-none',
          )}
          disabled={item.disabled}
          key={item.value}
          value={item.value}
        >
          {item.icon ? (
            <span className="flex size-10 shrink-0 items-center justify-center">
              {item.icon}
            </span>
          ) : null}
          <span className={cn(item.icon && 'max-sm:sr-only')}>
            {item.label}
          </span>
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
