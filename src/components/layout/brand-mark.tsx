import Image from 'next/image';
import { Typography } from '@/components/design-system';

import { AppLink } from '@/components/navigation';
import { routes } from '@/config/routes';

export function BrandMark() {
  return (
    <AppLink className="size-12 shrink-0" href={routes.home.path}>
      <Image
        alt="Orion"
        className="size-12 object-contain"
        height={48}
        src="/images/light-mode-transparent.svg"
        width={48}
      />
      <Typography as="span" variant="journalExcerpt">
        Orion
      </Typography>
    </AppLink>
  );
}
