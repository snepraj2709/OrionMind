import { describe, expect, it } from 'vitest';

import {
  reflectionApiResponseSchema,
  reflectionFeedbackRequestSchema,
  reflectionFeedbackResultSchema,
  processingInsightSchema,
  reflectionRequestSchema,
  reflectionSectionStatusSchema,
  unavailableInsightSchema,
} from './api-schema';
import { reflectionApiFixture } from './fixtures';

describe('reflection wire schemas', () => {
  it('parses the frozen aggregate response and feedback contracts', () => {
    expect(reflectionApiResponseSchema.parse(reflectionApiFixture)).toEqual(
      reflectionApiFixture,
    );
    expect(
      reflectionFeedbackRequestSchema.parse({ response: 'rejected' }),
    ).toEqual({ response: 'rejected' });
    expect(
      reflectionFeedbackResultSchema.parse({
        snapshotId: reflectionApiFixture.snapshot?.id,
        insightId:
          reflectionApiFixture.data.hiddenDriver.status === 'available'
            ? reflectionApiFixture.data.hiddenDriver.id
            : '',
        response: 'partly',
        updatedAt: '2026-07-21T12:42:00Z',
      }),
    ).toMatchObject({ response: 'partly' });
  });

  it.each([
    ['hiddenDriver', 'DRIVER_NOT_REPEATED'],
    ['recurringLoop', 'LOOP_NOT_REPEATED'],
    ['innerTensions', 'BOTH_SIDES_NOT_SUPPORTED'],
  ] as const)(
    'parses the valid %s insufficient union',
    (section, reasonCode) => {
      const response = structuredClone(reflectionApiFixture);
      const insufficient = {
        status: 'insufficient_evidence' as const,
        reasonCode,
        message: 'There is not enough repeated evidence yet.',
      };
      switch (section) {
        case 'hiddenDriver':
          response.data.hiddenDriver = insufficient;
          break;
        case 'recurringLoop':
          response.data.recurringLoop = insufficient;
          break;
        case 'innerTensions':
          response.data.innerTensions = insufficient;
          break;
      }

      expect(reflectionApiResponseSchema.parse(response)).toEqual(response);
    },
  );

  it('parses backend-exact zero-count, pending, and stale response states', () => {
    const zeroCount = structuredClone(reflectionApiFixture);
    zeroCount.reflectionState = 'insufficient_reflective_content';
    zeroCount.processingState = 'idle';
    zeroCount.snapshot = null;
    zeroCount.analysisBasis = {
      window: '90d',
      validEntryCount: 0,
      excludedEntryCount: 0,
      distinctEntryDates: 0,
      reflectiveWordCount: 0,
      currentRangeFrom: null,
      currentRangeTo: null,
      excludedReasons: null,
    };
    zeroCount.data = {
      hiddenDriver: {
        status: 'insufficient_evidence',
        reasonCode: 'NOT_ENOUGH_REFLECTIVE_CONTENT',
        message: 'There is not enough personal reflection yet.',
      },
      recurringLoop: {
        status: 'insufficient_evidence',
        reasonCode: 'LOOP_NOT_REPEATED',
        message: 'The same sequence has not repeated enough yet.',
      },
      innerTensions: {
        status: 'insufficient_evidence',
        reasonCode: 'BOTH_SIDES_NOT_SUPPORTED',
        message: 'There is not enough evidence for two competing needs yet.',
      },
    };

    const pending = structuredClone(zeroCount);
    pending.reflectionState = 'first_reflection_pending';
    pending.processingState = 'pending';

    const stale = structuredClone(reflectionApiFixture);
    stale.reflectionState = 'stale';
    stale.processingState = 'failed';
    if (stale.snapshot) stale.snapshot.isStale = true;

    expect(reflectionApiResponseSchema.parse(zeroCount)).toEqual(zeroCount);
    expect(reflectionApiResponseSchema.parse(pending)).toEqual(pending);
    expect(reflectionApiResponseSchema.parse(stale)).toEqual(stale);
  });

  it('accepts only the closed range request and no owner or tab fields', () => {
    expect(reflectionRequestSchema.parse({ range: '30d' })).toEqual({
      range: '30d',
    });
    expect(reflectionRequestSchema.safeParse({ range: '30D' }).success).toBe(
      false,
    );
    expect(
      reflectionRequestSchema.safeParse({
        range: '30d',
        userId: 'reader-id',
      }).success,
    ).toBe(false);
    expect(
      reflectionRequestSchema.safeParse({
        range: '30d',
        reflectionTab: 'hiddenDriver',
      }).success,
    ).toBe(false);
  });

  it('rejects unknown fields, unknown enums, and malformed insight variants', () => {
    expect(
      reflectionApiResponseSchema.safeParse({
        ...reflectionApiFixture,
        unexpected: true,
      }).success,
    ).toBe(false);
    expect(
      reflectionApiResponseSchema.safeParse({
        ...reflectionApiFixture,
        processingState: 'running',
      }).success,
    ).toBe(false);
    expect(
      reflectionApiResponseSchema.safeParse({
        ...reflectionApiFixture,
        data: {
          ...reflectionApiFixture.data,
          hiddenDriver: {
            status: 'available',
            reasonCode: 'DRIVER_NOT_REPEATED',
            message: 'Mixed union fields are invalid.',
          },
        },
      }).success,
    ).toBe(false);
    expect(
      reflectionFeedbackRequestSchema.safeParse({ response: 'accepted' })
        .success,
    ).toBe(false);
  });

  it('rejects missing sections, empty payloads, and empty available tensions', () => {
    const missingSection = structuredClone(reflectionApiFixture) as Record<
      string,
      unknown
    >;
    const data = missingSection.data as Record<string, unknown>;
    delete data.recurringLoop;

    expect(reflectionApiResponseSchema.safeParse({}).success).toBe(false);
    expect(reflectionApiResponseSchema.safeParse(missingSection).success).toBe(
      false,
    );
    expect(
      reflectionApiResponseSchema.safeParse({
        ...reflectionApiFixture,
        data: {
          ...reflectionApiFixture.data,
          innerTensions: { status: 'available', tensions: [] },
        },
      }).success,
    ).toBe(false);
  });

  it('rejects unknown nested evidence fields and invalid bounded values', () => {
    const hidden = reflectionApiFixture.data.hiddenDriver;
    if (hidden.status !== 'available') throw new Error('Fixture invariant');
    const malformed = structuredClone(reflectionApiFixture);
    if (malformed.data.hiddenDriver.status !== 'available') {
      throw new Error('Fixture invariant');
    }
    malformed.data.hiddenDriver.score = 1.1;
    expect(reflectionApiResponseSchema.safeParse(malformed).success).toBe(
      false,
    );
    expect(
      reflectionApiResponseSchema.safeParse({
        ...reflectionApiFixture,
        data: {
          ...reflectionApiFixture.data,
          hiddenDriver: {
            ...hidden,
            evidence: [{ ...hidden.evidence[0], rawOffset: 12 }],
          },
        },
      }).success,
    ).toBe(false);
    const invalidCount = structuredClone(reflectionApiFixture);
    if (invalidCount.data.hiddenDriver.status !== 'available') {
      throw new Error('Fixture invariant');
    }
    invalidCount.data.hiddenDriver.evidenceEntryCount = 0;
    expect(reflectionApiResponseSchema.safeParse(invalidCount).success).toBe(
      false,
    );
  });

  it('locks additive section states without changing existing aggregate parsing', () => {
    expect(reflectionSectionStatusSchema.options).toEqual([
      'available',
      'processing',
      'insufficient_evidence',
      'unavailable',
    ]);
    expect(
      processingInsightSchema.parse({
        status: 'processing',
        message: 'Your reflection is being recalculated.',
      }),
    ).toEqual({
      status: 'processing',
      message: 'Your reflection is being recalculated.',
    });
    expect(
      unavailableInsightSchema.parse({
        status: 'unavailable',
        reasonCode: 'TECHNICAL_FAILURE',
        message: 'This section is temporarily unavailable.',
        retryable: true,
      }),
    ).toMatchObject({ status: 'unavailable', retryable: true });
    expect(reflectionApiResponseSchema.parse(reflectionApiFixture)).toEqual(
      reflectionApiFixture,
    );
  });
});
