/** Test-only configurable repository used by unit tests. */
import { simulateLatency } from '@/services/mock-delay';

import { approvedEvidenceToReflectionEvidence } from './adapter';
import type {
  ReflectionApiResponse,
  ReflectionFeedbackResponse,
  ReflectionFeedbackResult,
  ReflectionRequest,
} from './api-schema';
import { buildReflectionApiResponse } from './response-builder';
import type {
  PutReflectionFeedbackInput,
  ReflectionsRepository,
} from './repository';

interface ReflectionEvidenceSource {
  listApprovedReflectionEvidence(): Array<{
    content: string;
    entryDate: string;
  }>;
}

interface MockReflectionsRepositoryOptions {
  response?: ReflectionApiResponse;
  delay?: number;
  evidenceSource?: ReflectionEvidenceSource;
}

function updateFeedback(
  aggregate: ReflectionApiResponse,
  insightId: string,
  response: ReflectionFeedbackResponse,
) {
  if (
    aggregate.data.hiddenDriver.status === 'available' &&
    aggregate.data.hiddenDriver.id === insightId
  ) {
    aggregate.data.hiddenDriver.feedback = response;
  }
  if (
    aggregate.data.recurringLoop.status === 'available' &&
    aggregate.data.recurringLoop.id === insightId
  ) {
    aggregate.data.recurringLoop.feedback = response;
  }
  if (aggregate.data.innerTensions.status === 'available') {
    const tension = aggregate.data.innerTensions.tensions.find(
      (item) => item.id === insightId,
    );
    if (tension) tension.feedback = response;
  }
}

export class MockReflectionsRepository implements ReflectionsRepository {
  private readonly delay: number;
  private readonly evidenceSource?: ReflectionEvidenceSource;
  private response: ReflectionApiResponse;

  constructor(options: MockReflectionsRepositoryOptions = {}) {
    this.delay = options.delay ?? 0;
    this.evidenceSource = options.evidenceSource;
    this.response = structuredClone(
      options.response ?? buildReflectionApiResponse(),
    );
  }

  async getReflection(input: ReflectionRequest) {
    await simulateLatency(this.delay);
    const result = structuredClone(this.response);
    result.range = input.range;
    const approvedEvidence = approvedEvidenceToReflectionEvidence(
      this.evidenceSource?.listApprovedReflectionEvidence() ?? [],
    );
    if (
      approvedEvidence.length > 0 &&
      result.data.hiddenDriver.status === 'available'
    ) {
      result.data.hiddenDriver.evidence = approvedEvidence;
    }
    return result;
  }

  async putFeedback(
    input: PutReflectionFeedbackInput,
  ): Promise<ReflectionFeedbackResult> {
    await simulateLatency(this.delay);
    updateFeedback(this.response, input.insightId, input.response);
    return {
      snapshotId: input.snapshotId,
      insightId: input.insightId,
      response: input.response,
      updatedAt: '2026-07-21T12:42:00Z',
    };
  }
}
