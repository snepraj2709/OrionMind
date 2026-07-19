import { Orbit } from 'lucide-react';

import { Typography } from '@/components/design-system';
import { AppLink } from '@/components/navigation';
import { routes } from '@/config/routes';

export function BrandMark() {
  return (
    <AppLink className="gap-3" href={routes.home.path}>
      <Orbit aria-hidden="true" className="icon-md text-primary" />
      <Typography as="span" variant="componentTitle">
        Orion
      </Typography>
    </AppLink>
  );
}
