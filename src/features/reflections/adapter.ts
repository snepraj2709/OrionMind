import type { EvidenceItem } from '@/types/evidence';

import type { JournalEntry, ReflectionViewModel } from './model';
import { reflectionCopyFixture } from './fixtures';

export function deriveReflectionEvidence(
  entries: JournalEntry[],
): EvidenceItem[] {
  return entries.flatMap((entry, entryIndex) => {
    const categories = [
      [
        reflectionCopyFixture.evidence.sources.addedEnergy,
        entry.content.added_energy,
      ],
      [
        reflectionCopyFixture.evidence.sources.drainedEnergy,
        entry.content.drained_energy,
      ],
      [
        reflectionCopyFixture.evidence.sources.selfKnowledge,
        entry.content.self_knowledge,
      ],
    ] as const;

    return categories.flatMap(([source, statements], categoryIndex) =>
      statements.map((text, statementIndex) => ({
        id: `${entry.entry_date}-${entryIndex}-${categoryIndex}-${statementIndex}`,
        date: entry.entry_date,
        interpretation: reflectionCopyFixture.evidence.interpretation,
        source,
        text,
      })),
    );
  });
}

export function deriveReflectionViewModel(
  entries: JournalEntry[],
): ReflectionViewModel {
  const sorted = [...entries].sort((left, right) =>
    left.entry_date.localeCompare(right.entry_date),
  );
  const evidence = deriveReflectionEvidence(sorted);
  const from = sorted[0]?.entry_date ?? null;
  const to = sorted.at(-1)?.entry_date ?? null;

  return {
    entryCount: sorted.length,
    from,
    to,
    hiddenDriver: {
      ...reflectionCopyFixture.hiddenDriver,
      drivers: [...reflectionCopyFixture.hiddenDriver.drivers],
      evidenceStrength: [
        ...reflectionCopyFixture.hiddenDriver.evidenceStrength,
      ],
      observedEntryCount: sorted.length,
      evidence: evidence.slice(0, 8),
    },
    loop: {
      ...reflectionCopyFixture.loop,
      steps: reflectionCopyFixture.loop.steps.map((step, index) => ({
        ...step,
        evidence: evidence.slice(index, index + 3),
      })),
      evidence: evidence.slice(3, 12),
    },
    innerTension: {
      title: reflectionCopyFixture.innerTension.title,
      tensions: reflectionCopyFixture.innerTension.tensions.map(
        (tension, index) => ({
          ...tension,
          dates:
            index === 0
              ? [from, to].filter((date): date is string => date !== null)
              : sorted.slice(1, 3).map((entry) => entry.entry_date),
          evidence: index === 0 ? evidence.slice(4, 10) : evidence.slice(9, 15),
        }),
      ),
    },
  };
}
