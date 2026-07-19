import { cloneElement, type ReactElement, type ReactNode } from 'react';

import { Typography } from '@/components/design-system';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

export interface FieldControlProps {
  id?: string;
  'aria-describedby'?: string;
  'aria-invalid'?: boolean;
}

export interface FormFieldProps {
  id: string;
  label: string;
  children:
    ReactElement<FieldControlProps> | ((props: FieldControlProps) => ReactNode);
  description?: ReactNode;
  error?: string;
  required?: boolean;
  className?: string;
}

export function FormField({
  children,
  className,
  description,
  error,
  id,
  label,
  required = false,
}: FormFieldProps) {
  const descriptionId = description ? `${id}-description` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy =
    [descriptionId, errorId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={cn('space-y-2', className)}>
      <Label className="type-metadata" htmlFor={id}>
        {label}
        {required ? (
          <span aria-hidden="true" className="text-destructive">
            {' '}
            *
          </span>
        ) : null}
      </Label>
      {typeof children === 'function'
        ? children({
            id,
            'aria-describedby': describedBy,
            'aria-invalid': error ? true : undefined,
          })
        : cloneElement(children, {
            id,
            'aria-describedby': describedBy,
            'aria-invalid': error ? true : undefined,
          })}
      {description ? (
        <Typography
          className="text-muted-foreground"
          id={descriptionId}
          variant="bodySmall"
        >
          {description}
        </Typography>
      ) : null}
      {error ? (
        <p
          className="type-body-small text-destructive"
          id={errorId}
          role="alert"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
