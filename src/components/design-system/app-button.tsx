import { LoaderCircle } from 'lucide-react';
import type { ComponentProps, ReactNode } from 'react';

import { Button as ShadcnButton } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export type AppButtonVariant =
  'primary' | 'secondary' | 'ghost' | 'destructive' | 'link' | 'icon';

export type AppButtonSize = 'default' | 'compact';
export type AppButtonShape = 'default' | 'pill';

export interface AppButtonProps extends Omit<
  ComponentProps<typeof ShadcnButton>,
  'size' | 'variant'
> {
  variant?: AppButtonVariant;
  size?: AppButtonSize;
  shape?: AppButtonShape;
  loading?: boolean;
  loadingLabel?: string;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

const variantClasses: Record<AppButtonVariant, string> = {
  primary:
    'bg-primary text-primary-foreground hover:bg-primary/90 active:bg-primary/80',
  secondary:
    'border border-border bg-secondary text-secondary-foreground hover:bg-muted',
  ghost: 'bg-transparent text-foreground hover:bg-muted',
  destructive:
    'bg-destructive text-destructive-foreground hover:bg-destructive/90',
  link: 'bg-transparent px-0 text-primary underline-offset-4 hover:underline',
  icon: 'bg-transparent p-0 text-foreground hover:bg-muted',
};

const sizeClasses: Record<AppButtonSize, string> = {
  default: 'control-default px-4',
  compact: 'control-compact px-3',
};

const shapeClasses: Record<AppButtonShape, string> = {
  default: 'radius-interactive',
  pill: 'radius-pill border border-border',
};

export function AppButton({
  'aria-label': ariaLabel,
  asChild,
  children,
  className,
  disabled,
  leftIcon,
  loading = false,
  loadingLabel = 'Loading',
  rightIcon,
  size = 'default',
  shape = 'default',
  variant = 'primary',
  ...props
}: AppButtonProps) {
  if (variant === 'icon' && !ariaLabel) {
    throw new Error('Icon-only buttons require an aria-label.');
  }

  const iconSizeClass =
    size === 'default' ? 'icon-control-default' : 'icon-control-compact';

  return (
    <ShadcnButton
      asChild={asChild}
      aria-busy={loading || undefined}
      aria-label={loading ? loadingLabel : ariaLabel}
      className={cn(
        'type-button focus-visible:ring-ring relative gap-2 transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50',
        shapeClasses[shape],
        variantClasses[variant],
        variant === 'icon' ? iconSizeClass : sizeClasses[size],
        className,
      )}
      disabled={disabled || loading}
      size={null}
      variant={null}
      {...props}
    >
      {asChild ? (
        children
      ) : (
        <>
          {loading ? (
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
          ) : (
            leftIcon
          )}
          {loading && variant === 'icon' ? null : children}
          {loading ? <span className="sr-only">{loadingLabel}</span> : null}
          {loading ? null : rightIcon}
        </>
      )}
    </ShadcnButton>
  );
}
