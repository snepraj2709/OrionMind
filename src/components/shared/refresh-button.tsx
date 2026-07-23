import { RefreshCw } from 'lucide-react';

import { AppButton, type AppButtonProps } from '@/components/design-system';

export type RefreshButtonProps = Omit<
  AppButtonProps,
  'leftIcon' | 'loading' | 'loadingLabel'
>;

export function RefreshButton({
  children,
  size = 'compact',
  variant = 'ghost',
  ...props
}: RefreshButtonProps) {
  const content = variant === 'icon' ? undefined : (children ?? 'Refresh');

  return (
    <AppButton
      leftIcon={<RefreshCw aria-hidden="true" className="size-4" />}
      size={size}
      variant={variant}
      {...props}
    >
      {content}
    </AppButton>
  );
}
