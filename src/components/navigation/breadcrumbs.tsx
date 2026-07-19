import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';

import { AppLink, type AppLinkProps } from './app-link';

export interface BreadcrumbItemModel {
  label: string;
  href?: AppLinkProps['href'];
}

export interface BreadcrumbsProps {
  items: BreadcrumbItemModel[];
}

export function Breadcrumbs({ items }: BreadcrumbsProps) {
  return (
    <Breadcrumb>
      <BreadcrumbList className="type-body-small gap-2">
        {items.map((item, index) => {
          const isCurrent = index === items.length - 1;

          return (
            <Fragment key={`${item.label}-${index}`}>
              <BreadcrumbItem>
                {isCurrent || !item.href ? (
                  <BreadcrumbPage className="type-body-small">
                    {item.label}
                  </BreadcrumbPage>
                ) : (
                  <BreadcrumbLink asChild>
                    <AppLink href={item.href}>{item.label}</AppLink>
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
              {isCurrent ? null : <BreadcrumbSeparator />}
            </Fragment>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
import { Fragment } from 'react';
