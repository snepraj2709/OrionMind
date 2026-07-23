'use client';

import { SelectField, type SelectOption } from '@/components/forms';

export interface FilterFieldProps {
  id: string;
  label: string;
  options: SelectOption[];
  value?: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  hideLabel?: boolean;
  disabled?: boolean;
}

export function FilterField(props: FilterFieldProps) {
  return (
    <div className="w-fit">
      <SelectField {...props} />
    </div>
  );
}
