import demoReflection from '../../../data/orion_30_day_reflection_analysis.json';

import type {
  EvidenceItem,
  InnerTension,
  ReflectionApiResponse,
  ReflectionFeedbackResponse,
} from './api-schema';
import type { ReflectionsRepository } from './repository';

type FixtureEvidence =
  (typeof demoReflection.data.hiddenDriver.evidence)[number];

function fixtureUuid(sequence: number) {
  return `00000000-0000-4000-8000-${String(sequence).padStart(12, '0')}`;
}

function adaptEvidence(item: FixtureEvidence, id: string): EvidenceItem {
  return {
    id,
    entryDate: item.date,
    sourceLabel: item.source,
    quote: item.text,
    interpretation: item.interpretation,
    theme: null,
    supports: item.interpretation,
  };
}

function adaptTension(
  tension: (typeof demoReflection.data.innerTension.tensions)[number],
  index: number,
): InnerTension {
  return {
    id: fixtureUuid(500 + index),
    confidence: 'recurring',
    score: 1,
    evidenceEntryCount: tension.evidence.length,
    leftTitle: tension.leftTitle as InnerTension['leftTitle'],
    leftBody: tension.leftBody,
    rightTitle: tension.rightTitle as InnerTension['rightTitle'],
    rightBody: tension.rightBody,
    integration: tension.integration,
    dates: tension.dates,
    evidence: tension.evidence.map((item, evidenceIndex) =>
      adaptEvidence(item, fixtureUuid(600 + index * 10 + evidenceIndex)),
    ),
    feedback: null,
  };
}

const fixtureResponse: ReflectionApiResponse = {
  range: '30d',
  reflectionState: 'available',
  processingState: 'idle',
  snapshot: {
    id: fixtureUuid(1),
    version: 1,
    generatedAt: `${demoReflection.period.to}T00:00:00.000Z`,
    sourceVersion: 1,
    isStale: false,
  },
  analysisBasis: {
    window: '90d',
    validEntryCount: demoReflection.period.entryCount,
    excludedEntryCount: 0,
    distinctEntryDates: demoReflection.period.entryCount,
    reflectiveWordCount: 0,
    currentRangeFrom: demoReflection.period.from,
    currentRangeTo: demoReflection.period.to,
    excludedReasons: null,
  },
  data: {
    hiddenDriver: {
      status: 'available',
      id: fixtureUuid(2),
      confidence: 'recurring',
      score: 1,
      evidenceEntryCount: demoReflection.data.hiddenDriver.evidence.length,
      evidence: demoReflection.data.hiddenDriver.evidence.map((item, index) =>
        adaptEvidence(item, fixtureUuid(100 + index)),
      ),
      feedback: null,
      statement: demoReflection.data.hiddenDriver.statement,
      underlyingNeed: demoReflection.data.hiddenDriver.underlyingNeed,
      drivers: demoReflection.data.hiddenDriver.drivers,
    },
    recurringLoop: {
      status: 'available',
      id: fixtureUuid(3),
      confidence: 'recurring',
      score: 1,
      evidenceEntryCount: demoReflection.data.recurringLoop.evidence.length,
      evidence: demoReflection.data.recurringLoop.evidence.map((item, index) =>
        adaptEvidence(item, fixtureUuid(200 + index)),
      ),
      feedback: null,
      title: demoReflection.data.recurringLoop.title,
      description: demoReflection.data.recurringLoop.description,
      steps: demoReflection.data.recurringLoop.steps.map((step, stepIndex) => ({
        id: fixtureUuid(300 + stepIndex),
        text: step.text,
        evidence: step.evidence.map((item, evidenceIndex) =>
          adaptEvidence(
            item,
            fixtureUuid(400 + stepIndex * 10 + evidenceIndex),
          ),
        ),
      })),
      protection: demoReflection.data.recurringLoop.protection,
      interruption: demoReflection.data.recurringLoop.interruption,
    },
    innerTensions: {
      status: 'available',
      tensions: demoReflection.data.innerTension.tensions.map(adaptTension),
    },
  },
};

const feedbackByInsightId = new Map<string, ReflectionFeedbackResponse>();

function applySessionFeedback(response: ReflectionApiResponse) {
  if (response.data.hiddenDriver.status === 'available') {
    response.data.hiddenDriver.feedback =
      feedbackByInsightId.get(response.data.hiddenDriver.id) ?? null;
  }
  if (response.data.recurringLoop.status === 'available') {
    response.data.recurringLoop.feedback =
      feedbackByInsightId.get(response.data.recurringLoop.id) ?? null;
  }
  if (response.data.innerTensions.status === 'available') {
    for (const tension of response.data.innerTensions.tensions) {
      tension.feedback = feedbackByInsightId.get(tension.id) ?? null;
    }
  }
  return response;
}

export const fixtureReflectionsRepository: ReflectionsRepository = {
  async getReflection(input) {
    return applySessionFeedback({
      ...structuredClone(fixtureResponse),
      range: input.range,
    });
  },
  async recalculate() {
    return { status: 'accepted', jobId: fixtureUuid(900) };
  },
  async putFeedback(input) {
    feedbackByInsightId.set(input.insightId, input.response);
    return { ...input, updatedAt: new Date().toISOString() };
  },
};
