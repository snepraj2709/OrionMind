import { RefreshCw } from 'lucide-react';

import { AppButton, type AppButtonProps } from '@/components/design-system';

export interface RefreshButtonProps extends Omit<
  AppButtonProps,
  'leftIcon' | 'loadingLabel'
> {
  loadingLabel: string;
}

export function RefreshButton({
  children,
  loadingLabel,
  size = 'compact',
  variant = 'ghost',
  ...props
}: RefreshButtonProps) {
  const content = variant === 'icon' ? undefined : (children ?? 'Refresh');

  return (
    <AppButton
      leftIcon={<RefreshCw aria-hidden="true" className="size-4" />}
      loadingLabel={loadingLabel}
      size={size}
      variant={variant}
      {...props}
    >
      {content}
    </AppButton>
  );
}
