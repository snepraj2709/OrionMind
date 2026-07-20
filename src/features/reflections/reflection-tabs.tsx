import { Infinity, Lightbulb, Zap } from 'lucide-react';
import type { ReactNode } from 'react';

import { SegmentedControl } from '@/components/navigation';

import type { ReflectionView } from './model';

export interface ReflectionTabsProps {
  value: ReflectionView;
  onValueChange: (value: ReflectionView) => void;
  panel: ReactNode;
}

const viewLabels: Record<ReflectionView, string> = {
  'hidden-drivers': 'Hidden drivers',
  'recurring-loops': 'Recurring loops',
  'inner-tensions': 'Inner tensions',
};

export function ReflectionTabs({
  onValueChange,
  panel,
  value,
}: ReflectionTabsProps) {
  return (
    <div className="space-y-6">
      <SegmentedControl
        ariaLabel="Reflection views"
        items={[
          {
            value: 'hidden-drivers',
            label: viewLabels['hidden-drivers'],
            icon: <Lightbulb aria-hidden="true" className="size-4" />,
          },
          {
            value: 'recurring-loops',
            label: viewLabels['recurring-loops'],
            icon: <Infinity aria-hidden="true" className="size-4" />,
          },
          {
            value: 'inner-tensions',
            label: viewLabels['inner-tensions'],
            icon: (
              <Zap
                aria-hidden="true"
                className="size-4"
                data-testid="inner-tensions-tab-icon"
              />
            ),
          },
        ]}
        onValueChange={(nextValue) =>
          onValueChange(nextValue as ReflectionView)
        }
        value={value}
      />
      <div aria-label={`${viewLabels[value]} reflection`} role="region">
        {panel}
      </div>
    </div>
  );
}
