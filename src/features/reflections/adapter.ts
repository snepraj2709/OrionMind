import type { EvidenceItem } from '@/types/evidence';

import type { JournalEntry, ReflectionViewModel } from './model';
import { reflectionCopyFixture } from './fixtures';

function deriveEvidence(entries: JournalEntry[]): EvidenceItem[] {
  return entries.flatMap((entry, entryIndex) => {
    const categories = [
      ['Energizing', entry.content.added_energy],
      ['Draining', entry.content.drained_energy],
      ['Self-knowledge', entry.content.self_knowledge],
    ] as const;

    return categories.flatMap(([source, statements], categoryIndex) =>
      statements.map((text, statementIndex) => ({
        id: `${entry.entry_date}-${entryIndex}-${categoryIndex}-${statementIndex}`,
        date: entry.entry_date,
        interpretation:
          'This sentence contributes to a pattern only when it appears alongside related journal evidence across the period.',
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
  const evidence = deriveEvidence(sorted);
  const from = sorted[0]?.entry_date ?? '';
  const to = sorted.at(-1)?.entry_date ?? '';

  return {
    entryCount: sorted.length,
    from,
    to,
    hiddenDriver: {
      ...reflectionCopyFixture.hiddenDriver,
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
    tensions: reflectionCopyFixture.tensions.map((tension, index) => ({
      ...tension,
      dates:
        index === 0
          ? [from, to].filter(Boolean)
          : sorted.slice(1, 3).map((entry) => entry.entry_date),
      evidence: index === 0 ? evidence.slice(4, 10) : evidence.slice(9, 15),
    })),
  };
}
