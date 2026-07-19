'use client';

import { cn } from '@/lib/utils';

import { FormField } from './form-field';
import { TextInput } from './text-input';

export interface DateRangeValue {
  start: string;
  end: string;
}

export interface DateRangeFieldProps {
  id: string;
  label: string;
  value: DateRangeValue;
  onChange: (value: DateRangeValue) => void;
  error?: string;
  disabled?: boolean;
  className?: string;
}

export function DateRangeField({
  className,
  disabled,
  error,
  id,
  label,
  onChange,
  value,
}: DateRangeFieldProps) {
  return (
    <fieldset className={cn('space-y-2', className)}>
      <legend className="type-metadata">{label}</legend>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormField id={`${id}-start`} label="Start date">
          <TextInput
            disabled={disabled}
            max={value.end || undefined}
            onChange={(event) =>
              onChange({ ...value, start: event.target.value })
            }
            type="date"
            value={value.start}
          />
        </FormField>
        <FormField error={error} id={`${id}-end`} label="End date">
          <TextInput
            disabled={disabled}
            min={value.start || undefined}
            onChange={(event) =>
              onChange({ ...value, end: event.target.value })
            }
            type="date"
            value={value.end}
          />
        </FormField>
      </div>
    </fieldset>
  );
}
