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
  default: 'data-[state=on]:bg-card data-[state=on]:text-primary',
  strong:
    'data-[state=on]:bg-selection-strong data-[state=on]:text-selection-strong-foreground',
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
        'radius-interactive border-border bg-muted max-w-full overflow-x-auto border p-1',
        className,
      )}
      defaultValue={defaultValue}
      onValueChange={(nextValue) => {
        if (nextValue) onValueChange?.(nextValue);
      }}
      type="single"
      value={value}
    >
      {items.map((item) => (
        <ToggleGroupItem
          className={cn(
            'type-button control-compact radius-control',
            itemVariantClasses[variant],
          )}
          disabled={item.disabled}
          key={item.value}
          value={item.value}
        >
          {item.icon}
          {item.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
