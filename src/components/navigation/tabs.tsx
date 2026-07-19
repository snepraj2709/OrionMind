'use client';

import type { ReactNode } from 'react';

import {
  Tabs as ShadcnTabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import { cn } from '@/lib/utils';

export interface TabItem {
  value: string;
  label: ReactNode;
  content: ReactNode;
  disabled?: boolean;
}

export interface TabsProps {
  items: TabItem[];
  defaultValue?: string;
  value?: string;
  onValueChange?: (value: string) => void;
  ariaLabel: string;
  className?: string;
}

export function Tabs({
  ariaLabel,
  className,
  defaultValue,
  items,
  onValueChange,
  value,
}: TabsProps) {
  return (
    <ShadcnTabs
      className={cn('gap-6', className)}
      defaultValue={defaultValue ?? items[0]?.value}
      onValueChange={onValueChange}
      value={value}
    >
      <TabsList
        aria-label={ariaLabel}
        className="radius-control min-touch-target max-w-full justify-start overflow-x-auto bg-transparent p-0"
        variant="line"
      >
        {items.map((item) => (
          <TabsTrigger
            className="type-navigation control-compact min-w-fit px-3"
            disabled={item.disabled}
            key={item.value}
            value={item.value}
          >
            {item.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {items.map((item) => (
        <TabsContent key={item.value} value={item.value}>
          {item.content}
        </TabsContent>
      ))}
    </ShadcnTabs>
  );
}
