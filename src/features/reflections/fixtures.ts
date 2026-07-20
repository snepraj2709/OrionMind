import type { JournalEntry } from './model';

export const reflectionCopyFixture = {
  evidence: {
    interpretation:
      'This sentence contributes to a pattern only when it appears alongside related journal evidence across the period.',
    sources: {
      addedEnergy: 'Energizing',
      drainedEnergy: 'Draining',
      selfKnowledge: 'Self-knowledge',
    },
  },
  hiddenDriver: {
    statement:
      'You appear most energised when curiosity becomes something tangible—understanding a difficult subject, making something, helping someone learn or developing a capability of your own.',
    underlyingNeed:
      'To experience yourself as capable, original and actively growing.',
    drivers: [
      'Curiosity and mastery',
      'Autonomy',
      'Meaningful connection',
      'Creative and physical vitality',
    ],
    evidenceStrength: [
      'Repeated across multiple entries',
      'Present across energising, draining and self-knowledge reflections',
      'Observed throughout this period',
    ],
  },
  loop: {
    title: 'A loop that may be keeping you stuck',
    description:
      'A possible pattern — offered as something to notice, not a conclusion.',
    steps: [
      {
        id: 'loop-1',
        text: 'A new idea or possibility creates energy.',
        entryCount: 4,
      },
      {
        id: 'loop-2',
        text: 'You begin exploring several directions.',
        entryCount: 5,
      },
      {
        id: 'loop-3',
        text: 'Your attention becomes fragmented.',
        entryCount: 6,
      },
      {
        id: 'loop-4',
        text: 'Progress starts feeling insufficient.',
        entryCount: 3,
      },
      {
        id: 'loop-5',
        text: 'Self-doubt or urgency appears.',
        entryCount: 4,
      },
      {
        id: 'loop-6',
        text: 'You seek more inspiration and new possibilities.',
        entryCount: 5,
      },
    ],
    protection:
      'The excitement of possibility without requiring you to risk choosing one direction.',
    interruption:
      'Turn one curiosity into one visible output before adding another.',
  },
  innerTension: {
    title: 'Needs you may be trying to hold at the same time',
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
      },
      {
        id: 'belonging-autonomy',
        leftTitle: 'Recognition and belonging',
        leftBody: 'You want to feel seen, valued and connected.',
        rightTitle: 'Autonomy and distinctiveness',
        rightBody:
          'You resist groups or expectations that do not feel true to you.',
        integration:
          'Seek recognition through work and relationships you genuinely respect.',
      },
    ],
  },
} as const;

const entryDates = [
  '2025-04-14',
  '2025-04-18',
  '2025-04-22',
  '2025-04-26',
  '2025-04-30',
  '2025-05-03',
  '2025-05-06',
  '2025-05-08',
] as const;

const entryPatterns: JournalEntry['content'][] = [
  {
    added_energy: [
      'Explaining a difficult idea to someone else made the whole subject click for me.',
    ],
    drained_energy: [
      'I kept opening new directions before finishing the one in front of me.',
    ],
    self_knowledge: [
      'I feel most capable when curiosity becomes something I can make or share.',
    ],
  },
  {
    added_energy: [
      'The open afternoon gave me room to follow one question all the way through.',
    ],
    drained_energy: [
      'By evening I was measuring progress against every idea I had not chosen.',
    ],
    self_knowledge: [
      'Autonomy matters, but I still want visible proof that my effort is becoming real.',
    ],
  },
  {
    added_energy: [
      'A long run and an hour of painting left me feeling alert and fully present.',
    ],
    drained_energy: [
      'Pushing through poor sleep made even simple decisions feel heavy.',
    ],
    self_knowledge: [
      'Intensity gives me momentum, but consistency is what keeps me able to continue.',
    ],
  },
  {
    added_energy: [
      'A thoughtful conversation made me feel seen without needing to perform.',
    ],
    drained_energy: [
      'Trying to fit the group expectation made me feel less like myself.',
    ],
    self_knowledge: [
      'Recognition only restores me when it comes from people and work I respect.',
    ],
  },
  {
    added_energy: [
      'Turning a loose thought into a small working sketch gave the day a clear shape.',
    ],
    drained_energy: [
      'I searched for more inspiration when the current project became uncertain.',
    ],
    self_knowledge: [
      'Possibility feels safe because choosing one direction makes failure more visible.',
    ],
  },
];

export const reflectionEntryFixtures: JournalEntry[] = entryDates.map(
  (entry_date, index) => ({
    entry_date,
    content: entryPatterns[index % entryPatterns.length]!,
  }),
);
