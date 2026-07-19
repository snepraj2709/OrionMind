'use client';

import { SelectField, type SelectOption } from '@/components/forms';

export interface FilterFieldProps {
  id: string;
  label: string;
  options: SelectOption[];
  value?: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
}

export function FilterField(props: FilterFieldProps) {
  return <SelectField {...props} />;
}
