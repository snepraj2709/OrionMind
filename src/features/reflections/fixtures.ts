/** Test-only aggregate fixtures. Production code must use the HTTP repository. */
import type { EvidenceItem, ReflectionApiResponse } from './api-schema';

export const reflectionFixtureIds = {
  snapshot: '10000000-0000-4000-8000-000000000001',
  hiddenDriver: '10000000-0000-4000-8000-000000000002',
  recurringLoop: '10000000-0000-4000-8000-000000000003',
  tensionOne: '10000000-0000-4000-8000-000000000004',
  tensionTwo: '10000000-0000-4000-8000-000000000005',
} as const;

export const reflectionEvidenceFixture: EvidenceItem[] = [
  {
    id: '20000000-0000-4000-8000-000000000001',
    entryDate: '2026-07-14',
    sourceLabel: 'Self-knowledge',
    quote:
      'Explaining a difficult idea to someone else made the whole subject click for me.',
    interpretation:
      'Curiosity becomes energizing when it turns into something tangible and shared.',
    theme: 'personal_growth',
    supports: 'Curiosity becoming something tangible',
  },
  {
    id: '20000000-0000-4000-8000-000000000002',
    entryDate: '2026-07-18',
    sourceLabel: 'Draining',
    quote:
      'I kept opening new directions before finishing the one in front of me.',
    interpretation:
      'New possibilities can interrupt progress on the direction already chosen.',
    theme: 'career',
    supports: 'The exploration-to-fragmentation transition',
  },
  {
    id: '20000000-0000-4000-8000-000000000003',
    entryDate: '2026-07-21',
    sourceLabel: 'Self-knowledge',
    quote:
      'Recognition restores me only when it comes from people and work I respect.',
    interpretation:
      'Belonging and autonomy both matter in the conditions you choose.',
    theme: 'family_friends',
    supports: 'The tension between belonging and autonomy',
  },
];

export const reflectionApiFixture: ReflectionApiResponse = {
  range: 'all',
  reflectionState: 'available',
  processingState: 'idle',
  snapshot: {
    id: reflectionFixtureIds.snapshot,
    version: 4,
    generatedAt: '2026-07-21T12:35:00Z',
    sourceVersion: 148,
    isStale: false,
  },
  analysisBasis: {
    window: '90d',
    validEntryCount: 8,
    excludedEntryCount: 1,
    distinctEntryDates: 8,
    reflectiveWordCount: 940,
    currentRangeFrom: '2026-07-14',
    currentRangeTo: '2026-07-21',
    excludedReasons: { test_or_noise: 1 },
  },
  data: {
    hiddenDriver: {
      status: 'available',
      id: reflectionFixtureIds.hiddenDriver,
      confidence: 'emerging',
      score: 0.74,
      evidenceEntryCount: 2,
      evidence: reflectionEvidenceFixture.slice(0, 2),
      feedback: null,
      statement:
        'You appear most energised when curiosity becomes something tangible.',
      underlyingNeed: 'To experience yourself as capable and actively growing.',
      drivers: ['Curiosity and mastery', 'Autonomy', 'Meaningful connection'],
    },
    recurringLoop: {
      status: 'available',
      id: reflectionFixtureIds.recurringLoop,
      confidence: 'recurring',
      score: 0.82,
      evidenceEntryCount: 2,
      evidence: reflectionEvidenceFixture.slice(1),
      feedback: 'partly',
      title: 'A loop that may be keeping you stuck',
      description:
        'A possible pattern — offered as something to notice, not a conclusion.',
      steps: [
        {
          id: '30000000-0000-4000-8000-000000000001',
          text: 'A new idea or possibility creates energy.',
          evidence: reflectionEvidenceFixture.slice(0, 1),
        },
        {
          id: '30000000-0000-4000-8000-000000000002',
          text: 'You begin exploring several directions.',
          evidence: reflectionEvidenceFixture.slice(1, 2),
        },
        {
          id: '30000000-0000-4000-8000-000000000003',
          text: 'Your attention becomes fragmented.',
          evidence: reflectionEvidenceFixture.slice(1, 2),
        },
      ],
      protection:
        'The excitement of possibility without requiring you to risk choosing one direction.',
      interruption:
        'Turn one curiosity into one visible output before adding another.',
    },
    innerTensions: {
      status: 'available',
      tensions: [
        {
          id: reflectionFixtureIds.tensionOne,
          confidence: 'emerging',
          score: 0.71,
          evidenceEntryCount: 2,
          leftTitle: 'novelty',
          leftBody: 'You gain energy from discovering new possibilities.',
          rightTitle: 'mastery',
          rightBody: 'You also want effort to become something complete.',
          integration:
            'Keep a place for new ideas while letting one become active work.',
          dates: ['2026-07-14', '2026-07-18'],
          evidence: reflectionEvidenceFixture.slice(0, 2),
          feedback: null,
        },
        {
          id: reflectionFixtureIds.tensionTwo,
          confidence: 'preliminary',
          score: 0.63,
          evidenceEntryCount: 1,
          leftTitle: 'belonging',
          leftBody: 'You want to feel seen, valued and connected.',
          rightTitle: 'autonomy',
          rightBody: 'You resist expectations that do not feel true to you.',
          integration:
            'Seek recognition through work and relationships you respect.',
          dates: ['2026-07-21'],
          evidence: reflectionEvidenceFixture.slice(2),
          feedback: 'rejected',
        },
      ],
    },
  },
};
