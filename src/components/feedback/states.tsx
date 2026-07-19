import { AlertTriangle, CircleDashed, SearchX } from 'lucide-react';
import type { ReactNode } from 'react';

import { Surface } from '@/components/cards';
import { Typography } from '@/components/design-system';
import { cn } from '@/lib/utils';

interface StateFrameProps {
  title: string;
  description: string;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
  role?: 'alert' | 'status';
}

function StateFrame({
  action,
  className,
  description,
  icon,
  role,
  title,
}: StateFrameProps) {
  return (
    <div
      className={cn(
        'text-measure mx-auto flex flex-col items-center gap-4 text-center',
        className,
      )}
      role={role}
    >
      {icon ? (
        <span aria-hidden="true" className="text-muted-foreground">
          {icon}
        </span>
      ) : null}
      <div className="space-y-2">
        <Typography as="h2" variant="reflectiveStatement">
          {title}
        </Typography>
        <Typography className="text-muted-foreground" variant="body">
          {description}
        </Typography>
      </div>
      {action}
    </div>
  );
}

export interface PageErrorStateProps {
  title?: string;
  description: string;
  action?: ReactNode;
  className?: string;
}

export function PageErrorState({
  action,
  className,
  description,
  title = 'Something went wrong',
}: PageErrorStateProps) {
  return (
    <Surface className={cn('px-6 py-12', className)}>
      <StateFrame
        action={action}
        description={description}
        icon={<AlertTriangle className="size-6" />}
        role="alert"
        title={title}
      />
    </Surface>
  );
}

export interface InlineErrorProps {
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function InlineError({ action, children, className }: InlineErrorProps) {
  return (
    <div
      className={cn(
        'radius-control border-destructive/40 bg-destructive/10 text-destructive flex items-start gap-3 border p-4',
        className,
      )}
      role="alert"
    >
      <AlertTriangle aria-hidden="true" className="mt-1 size-4 shrink-0" />
      <div className="type-body-small min-w-0 flex-1">{children}</div>
      {action}
    </div>
  );
}

export interface EmptyStateProps {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: ReactNode;
  className?: string;
}

export function EmptyState({
  action,
  className,
  description,
  icon = <CircleDashed className="size-6" />,
  title,
}: EmptyStateProps) {
  return (
    <StateFrame
      action={action}
      className={cn('py-12', className)}
      description={description}
      icon={icon}
      role="status"
      title={title}
    />
  );
}

export interface NoResultsStateProps extends Omit<
  EmptyStateProps,
  'description' | 'icon' | 'title'
> {
  title?: string;
  description?: string;
}

export function NoResultsState({
  action,
  className,
  description = 'Try adjusting or clearing your filters.',
  title = 'No matching results',
}: NoResultsStateProps) {
  return (
    <EmptyState
      action={action}
      className={className}
      description={description}
      icon={<SearchX className="size-6" />}
      title={title}
    />
  );
}

export interface ProcessingStateProps {
  title?: string;
  description: string;
  className?: string;
}

export function ProcessingState({
  className,
  description,
  title = 'Processing',
}: ProcessingStateProps) {
  return (
    <div
      aria-live="polite"
      className={cn(
        'radius-card border-border bg-card flex items-start gap-4 border p-6',
        className,
      )}
      role="status"
    >
      <CircleDashed
        aria-hidden="true"
        className="icon-md text-primary mt-1 animate-spin"
      />
      <div className="space-y-1">
        <Typography as="h3" variant="componentTitle">
          {title}
        </Typography>
        <Typography className="text-muted-foreground" variant="bodySmall">
          {description}
        </Typography>
      </div>
    </div>
  );
}

export interface FullScreenStateProps {
  children: ReactNode;
  contained?: boolean;
  className?: string;
}

export function FullScreenState({
  children,
  className,
  contained = false,
}: FullScreenStateProps) {
  return (
    <div
      className={cn(
        'flex w-full items-center justify-center p-6',
        contained ? 'min-state-contained' : 'min-h-screen',
        className,
      )}
    >
      {children}
    </div>
  );
}
