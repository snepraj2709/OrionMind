import type { Route } from 'next';

import { Typography } from '@/components/design-system';
import { AppLink } from '@/components/navigation';

export interface AuthRoutePromptProps {
  actionLabel: string;
  href: Route;
  prompt: string;
}

export function AuthRoutePrompt({
  actionLabel,
  href,
  prompt,
}: AuthRoutePromptProps) {
  return (
    <Typography className="text-muted-foreground" variant="bodySmall">
      {prompt}{' '}
      <AppLink
        className="type-metadata underline underline-offset-4"
        href={href}
      >
        {actionLabel}
      </AppLink>
    </Typography>
  );
}
