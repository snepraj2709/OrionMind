'use client';

import { Menu, X } from 'lucide-react';
import { type MouseEvent, type ReactNode, useState } from 'react';

import { AppButton, Typography } from '@/components/design-system';
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { cn } from '@/lib/utils';

export interface MobileNavigationProps {
  children: ReactNode;
  brand: ReactNode;
  title?: string;
  description?: string;
  className?: string;
}

export function MobileNavigation({
  brand,
  children,
  className,
  description = 'Navigate Orion',
  title = 'Menu',
}: MobileNavigationProps) {
  const [open, setOpen] = useState(false);

  function closeAfterNavigation(event: MouseEvent<HTMLElement>) {
    if (event.target instanceof Element && event.target.closest('a[href]')) {
      setOpen(false);
    }
  }

  return (
    <header
      className={cn(
        'border-border bg-background sticky top-0 z-40 flex min-h-16 items-center justify-between border-b px-4',
        className,
      )}
    >
      {brand}
      <Sheet onOpenChange={setOpen} open={open}>
        <SheetTrigger asChild>
          <AppButton aria-label="Open navigation" variant="icon">
            <Menu aria-hidden="true" className="icon-md" />
          </AppButton>
        </SheetTrigger>
        <SheetContent
          className="bg-sidebar w-full sm:max-w-md"
          showCloseButton={false}
          side="left"
        >
          <SheetHeader className="border-border border-b">
            <div className="flex items-center justify-between gap-4">
              <SheetTitle asChild>
                <Typography as="h2" variant="componentTitle">
                  {title}
                </Typography>
              </SheetTitle>
              <SheetClose asChild>
                <AppButton aria-label="Close navigation" variant="icon">
                  <X aria-hidden="true" className="icon-md" />
                </AppButton>
              </SheetClose>
            </div>
            <SheetDescription>{description}</SheetDescription>
          </SheetHeader>
          <nav
            aria-label="Mobile navigation"
            className="min-h-0 flex-1 overflow-y-auto p-4"
            onClick={closeAfterNavigation}
          >
            {children}
          </nav>
        </SheetContent>
      </Sheet>
    </header>
  );
}
