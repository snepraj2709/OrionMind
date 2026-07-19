'use client';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { FormField } from './form-field';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectFieldProps {
  id: string;
  label: string;
  options: SelectOption[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  placeholder?: string;
  description?: string;
  error?: string;
  required?: boolean;
  disabled?: boolean;
  name?: string;
}

export function SelectField({
  defaultValue,
  description,
  disabled,
  error,
  id,
  label,
  name,
  onValueChange,
  options,
  placeholder = 'Select an option',
  required,
  value,
}: SelectFieldProps) {
  return (
    <FormField
      description={description}
      error={error}
      id={id}
      label={label}
      required={required}
    >
      {(fieldProps) => (
        <Select
          defaultValue={defaultValue}
          disabled={disabled}
          name={name}
          onValueChange={onValueChange}
          value={value}
        >
          <SelectTrigger
            {...fieldProps}
            className="type-body control-default radius-interactive bg-input-background w-full shadow-none"
          >
            <SelectValue placeholder={placeholder} />
          </SelectTrigger>
          <SelectContent>
            {options.map((option) => (
              <SelectItem
                className="type-body min-touch-target radius-control px-2 py-2"
                disabled={option.disabled}
                key={option.value}
                value={option.value}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </FormField>
  );
}
