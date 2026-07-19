'use client';

import type { SelectOption } from '@/components/forms';
import { SelectField } from '@/components/forms';

export type SortDirection = 'asc' | 'desc';

export interface SortValue {
  columnId: string;
  direction: SortDirection;
}

export interface SortControlProps {
  columns: SelectOption[];
  value: SortValue;
  onChange: (value: SortValue) => void;
  id?: string;
}

export function SortControl({
  columns,
  id = 'table-sort',
  onChange,
  value,
}: SortControlProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row">
      <SelectField
        id={`${id}-column`}
        label="Sort by"
        onValueChange={(columnId) => onChange({ ...value, columnId })}
        options={columns}
        value={value.columnId}
      />
      <SelectField
        id={`${id}-direction`}
        label="Direction"
        onValueChange={(direction) =>
          onChange({ ...value, direction: direction as SortDirection })
        }
        options={[
          { value: 'asc', label: 'Ascending' },
          { value: 'desc', label: 'Descending' },
        ]}
        value={value.direction}
      />
    </div>
  );
}
