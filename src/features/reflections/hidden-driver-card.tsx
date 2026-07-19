import { Check } from 'lucide-react';

import { ReflectionCard } from '@/components/cards';
import { AppButton, Typography } from '@/components/design-system';
import type { ReflectionViewModel } from './model';

export type ResonanceValue = 'resonates' | 'partly' | 'rejected';

export interface HiddenDriverCardProps {
  driver: ReflectionViewModel['hiddenDriver'];
  resonance?: ResonanceValue;
  onResonanceChange: (value: ResonanceValue) => void;
  onViewEvidence: () => void;
}

export function HiddenDriverCard({
  driver,
  onResonanceChange,
  onViewEvidence,
  resonance,
}: HiddenDriverCardProps) {
  return (
    <ReflectionCard
      className={resonance === 'rejected' ? 'bg-muted' : undefined}
      footer={
        <div className="w-full space-y-4">
          <div className="flex flex-wrap gap-2">
            <AppButton
              aria-pressed={resonance === 'resonates'}
              onClick={() => onResonanceChange('resonates')}
              size="compact"
              variant={resonance === 'resonates' ? 'secondary' : 'ghost'}
            >
              This resonates
            </AppButton>
            <AppButton
              aria-pressed={resonance === 'partly'}
              onClick={() => onResonanceChange('partly')}
              size="compact"
              variant={resonance === 'partly' ? 'secondary' : 'ghost'}
            >
              Partly true
            </AppButton>
            <AppButton
              aria-pressed={resonance === 'rejected'}
              onClick={() => onResonanceChange('rejected')}
              size="compact"
              variant={resonance === 'rejected' ? 'secondary' : 'ghost'}
            >
              Not true for me
            </AppButton>
            <AppButton onClick={onViewEvidence} size="compact" variant="link">
              View supporting entries
            </AppButton>
          </div>
          {resonance === 'rejected' ? (
            <Typography
              aria-live="polite"
              className="text-muted-foreground"
              variant="bodySmall"
            >
              Marked as not true for you. Orion will not treat this as an
              accepted self-pattern.
            </Typography>
          ) : null}
        </div>
      }
      statement={driver.statement}
      supportingText={
        <span className="space-y-6">
          <span className="block space-y-2">
            <span className="type-eyebrow block">Possible underlying need</span>
            <span className="type-body-large text-foreground block">
              {driver.underlyingNeed}
            </span>
          </span>
          <span className="flex flex-wrap gap-2">
            {driver.drivers.map((item) => (
              <span
                className="type-metadata radius-pill bg-secondary text-foreground px-3 py-2"
                key={item}
              >
                {item}
              </span>
            ))}
          </span>
          <span className="border-border grid gap-3 border-t pt-6 md:grid-cols-3">
            {driver.evidenceStrength.map((item) => (
              <span className="type-body-small flex gap-2" key={item}>
                <Check
                  aria-hidden="true"
                  className="text-accent mt-1 size-4 shrink-0"
                />
                {item}
              </span>
            ))}
          </span>
          <AppButton onClick={onViewEvidence} size="compact" variant="link">
            Why am I seeing this?
          </AppButton>
        </span>
      }
      title="What seems to drive you"
    />
  );
}
