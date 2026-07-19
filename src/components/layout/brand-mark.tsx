import { Typography } from '@/components/design-system';
import { AppLink } from '@/components/navigation';
import { routes } from '@/config/routes';

export function BrandMark() {
  return (
    <AppLink className="gap-4" href={routes.home.path}>
      <span aria-hidden="true" className="flex items-end gap-1">
        <span className="bg-foreground/20 radius-pill size-2" />
        <span className="bg-foreground/50 radius-pill size-3" />
        <span className="bg-foreground/20 radius-pill size-2" />
      </span>
      <Typography as="span" variant="brandWordmarkProminent">
        Orion
      </Typography>
    </AppLink>
  );
}
