import type { EvidenceItem } from '@/types/evidence';

import type { JournalEntry, ReflectionViewModel } from './model';

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
      statement:
        'You appear most energized when curiosity becomes something tangible—understanding a difficult subject, making something, helping someone learn, or developing a capability of your own.',
      underlyingNeed:
        'To experience yourself as capable, original, and actively growing.',
      drivers: [
        'Curiosity and mastery',
        'Autonomy',
        'Meaningful connection',
        'Creative and physical vitality',
      ],
      evidenceStrength: [
        'Repeated across multiple entries',
        'Present across energizing, draining, and self-knowledge reflections',
        'Observed throughout this period',
      ],
      evidence: evidence.slice(0, 8),
    },
    loop: {
      steps: [
        'A new idea or possibility creates energy.',
        'You begin exploring several directions.',
        'Your attention becomes fragmented.',
        'Progress starts feeling insufficient.',
        'Self-doubt or urgency appears.',
        'You seek more inspiration and new possibilities.',
      ].map((text, index) => ({
        id: `loop-${index + 1}`,
        text,
        evidence: evidence.slice(index, index + 3),
      })),
      protection:
        'The excitement of possibility without requiring you to risk choosing one direction.',
      interruption:
        'Turn one curiosity into one visible output before adding another.',
      evidence: evidence.slice(3, 12),
    },
    tensions: [
      {
        id: 'novelty-focus',
        leftTitle: 'Novelty and exploration',
        leftBody:
          'You gain energy from discovering new ideas and possibilities.',
        rightTitle: 'Focus and completion',
        rightBody:
          'You also want evidence that your effort is producing something real.',
        integration:
          'Keep a place for new ideas, while letting only one become active work.',
        dates: [from, to].filter(Boolean),
        evidence: evidence.slice(4, 10),
      },
      {
        id: 'belonging-autonomy',
        leftTitle: 'Recognition and belonging',
        leftBody: 'You want to feel seen, valued, and connected.',
        rightTitle: 'Autonomy and distinctiveness',
        rightBody:
          'You resist groups or expectations that do not feel true to you.',
        integration:
          'Seek recognition through work and relationships you genuinely respect.',
        dates: sorted.slice(1, 3).map((entry) => entry.entry_date),
        evidence: evidence.slice(9, 15),
      },
      {
        id: 'intensity-sustainability',
        leftTitle: 'Intensity',
        leftBody:
          'You are drawn to maximum effort, physical movement, and rapid growth.',
        rightTitle: 'Sustainable energy',
        rightBody:
          'Sleep disruption, physical fatigue, and excessive pressure repeatedly reduce your capacity.',
        integration:
          'Consistency may take you further than bursts of maximum effort.',
        dates: sorted.slice(-3, -1).map((entry) => entry.entry_date),
        evidence: evidence.slice(14, 20),
      },
    ],
    focus: {
      title: 'Convert curiosity into evidence',
      body: 'Choose one idea that currently gives you energy and turn it into one visible output before beginning another.',
      experiment:
        'For the next seven days, protect one focused block for a single project. Keep new ideas in a backlog instead of making them active immediately.',
      evidence: evidence.slice(0, 12),
    },
  };
}
