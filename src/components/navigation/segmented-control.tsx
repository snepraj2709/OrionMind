'use client';

import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { cn } from '@/lib/utils';

export interface SegmentedControlItem {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SegmentedControlProps {
  items: SegmentedControlItem[];
  ariaLabel: string;
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  className?: string;
}

export function SegmentedControl({
  ariaLabel,
  className,
  defaultValue,
  items,
  onValueChange,
  value,
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
          className="type-button control-compact radius-control data-[state=on]:bg-card data-[state=on]:text-primary"
          disabled={item.disabled}
          key={item.value}
          value={item.value}
        >
          {item.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
