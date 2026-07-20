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
}

const itemVariantClasses = {
  default:
    'data-[state=on]:bg-card data-[state=on]:text-foreground data-[state=on]:shadow-selected-control',
  strong:
    'data-[state=on]:bg-selection-strong data-[state=on]:text-selection-strong-foreground data-[state=on]:shadow-selected-control',
} as const;

export function SegmentedControl({
  ariaLabel,
  className,
  defaultValue,
  items,
  onValueChange,
  value,
  variant = 'default',
}: SegmentedControlProps) {
  return (
    <ToggleGroup
      aria-label={ariaLabel}
      className={cn(
        'radius-surface border-border bg-muted max-w-full gap-1 overflow-x-auto border p-1',
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
            'type-navigation control-prominent radius-card text-muted-foreground hover:bg-card/60 hover:text-foreground gap-0 px-4',
            itemVariantClasses[variant],
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
