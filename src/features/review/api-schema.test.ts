import { describe, expect, it } from 'vitest';

import {
  entryInsightCategorySchema,
  entryInsightFeedbackRequestSchema,
  entryInsightTypeSchema,
  entryInsightVerdictSchema,
  feedbackRequestSchemaForScope,
  patternCategorySchema,
  patternFeedbackRequestSchema,
  patternTypeSchema,
  patternVerdictSchema,
  reviewCategoryFilterSchema,
  reviewCorrectionMaxLength,
  reviewScopeSchema,
  reviewSourceQuoteMaxLength,
  reviewStatementMaxLength,
  reviewItemsResponseSchema,
  reviewListQuerySchema,
  reviewNoteMaxLength,
  reviewStatusSchema,
  inferenceLevelSchema,
} from './api-schema';

const itemId = '81111111-1111-4111-8111-111111111111';
const entryId = '82222222-2222-4222-8222-222222222222';
const secondEntryId = '83333333-3333-4333-8333-333333333333';

function entryItem() {
  return {
    id: itemId,
    scope: 'entry_insight' as const,
    type: 'energy_loss' as const,
    category: 'energy' as const,
    statement: 'Preparing at the last minute drained your energy.',
    sourceQuote: 'The rushed preparation was exhausting.',
    sourceEntryIds: [entryId],
    sourceDates: ['2026-07-20'],
    inferenceLevel: 'direct' as const,
    confidence: 0.94,
    status: 'pending' as const,
    feedback: null,
  };
}

function patternItem() {
  return {
    id: itemId,
    scope: 'pattern' as const,
    type: 'hidden_driver' as const,
    category: 'hidden_driver' as const,
    statement: 'Perfection may protect you from being evaluated.',
    sourceQuote: null,
    sourceEntryIds: [entryId, secondEntryId],
    sourceDates: ['2026-07-20', '2026-07-22'],
    inferenceLevel: 'synthesized' as const,
    confidence: 0.82,
    status: 'partially_confirmed' as const,
    feedback: {
      verdict: 'partly_true' as const,
      correctedStatement: null,
      note: 'This fits only around work.',
      evidenceWeight: 0.5 as const,
      updatedAt: '2026-07-23T10:30:00Z',
    },
  };
}

describe('review wire schemas', () => {
  it('locks every public enum value', () => {
    expect(entryInsightTypeSchema.options).toEqual([
      'energy_gain',
      'energy_loss',
      'self_knowledge',
      'realization',
      'explicit_preference',
      'need',
      'belief',
      'avoidance',
      'protective_strategy',
      'conflict',
      'causal_relationship',
    ]);
    expect(patternTypeSchema.options).toEqual([
      'hidden_driver',
      'recurring_loop',
      'inner_tension',
    ]);
    expect(entryInsightCategorySchema.options).toEqual([
      'energy',
      'self_knowledge',
      'needs_beliefs',
    ]);
    expect(patternCategorySchema.options).toEqual([
      'hidden_driver',
      'recurring_loop',
      'inner_tension',
    ]);
    expect(reviewStatusSchema.options).toEqual([
      'pending',
      'confirmed',
      'partially_confirmed',
      'rejected',
    ]);
    expect(entryInsightVerdictSchema.options).toEqual([
      'accurate',
      'partly_accurate',
      'not_accurate',
    ]);
    expect(patternVerdictSchema.options).toEqual([
      'resonates',
      'partly_true',
      'not_true',
    ]);
    expect(reviewScopeSchema.options).toEqual(['entry_insight', 'pattern']);
    expect(reviewCategoryFilterSchema.options).toEqual([
      'all',
      'energy',
      'self_knowledge',
      'needs_beliefs',
      'hidden_driver',
      'recurring_loop',
      'inner_tension',
    ]);
    expect(inferenceLevelSchema.options).toEqual([
      'direct',
      'inferred',
      'synthesized',
    ]);
  });

  it.each([
    ['entry_insight', 'energy'],
    ['entry_insight', 'self_knowledge'],
    ['entry_insight', 'needs_beliefs'],
    ['pattern', 'hidden_driver'],
    ['pattern', 'recurring_loop'],
    ['pattern', 'inner_tension'],
  ] as const)('accepts %s with its %s category', (scope, category) => {
    expect(reviewListQuerySchema.parse({ scope, category })).toEqual({
      scope,
      category,
      status: 'pending',
      page: 1,
      page_size: 20,
    });
  });

  it.each([
    ['entry_insight', 'hidden_driver'],
    ['entry_insight', 'recurring_loop'],
    ['entry_insight', 'inner_tension'],
    ['pattern', 'energy'],
    ['pattern', 'self_knowledge'],
    ['pattern', 'needs_beliefs'],
  ] as const)(
    'rejects %s with the cross-scope %s category',
    (scope, category) => {
      expect(reviewListQuerySchema.safeParse({ scope, category }).success).toBe(
        false,
      );
    },
  );

  it('rejects unknown query fields and page bounds', () => {
    expect(
      reviewListQuerySchema.safeParse({
        scope: 'entry_insight',
        unexpected: true,
      }).success,
    ).toBe(false);
    expect(
      reviewListQuerySchema.safeParse({
        scope: 'entry_insight',
        page: 0,
      }).success,
    ).toBe(false);
    expect(
      reviewListQuerySchema.safeParse({
        scope: 'entry_insight',
        page_size: 101,
      }).success,
    ).toBe(false);
  });

  it.each(['accurate', 'partly_accurate', 'not_accurate'] as const)(
    'accepts the Entry Insight %s verdict only for Entry Insight',
    (verdict) => {
      const body = { verdict, correctedStatement: null, note: null };
      expect(entryInsightFeedbackRequestSchema.parse(body)).toEqual(body);
      expect(
        feedbackRequestSchemaForScope('pattern').safeParse(body).success,
      ).toBe(false);
    },
  );

  it.each(['resonates', 'partly_true', 'not_true'] as const)(
    'accepts the Pattern %s verdict only for Pattern',
    (verdict) => {
      const body = { verdict, correctedStatement: null, note: null };
      expect(patternFeedbackRequestSchema.parse(body)).toEqual(body);
      expect(
        feedbackRequestSchemaForScope('entry_insight').safeParse(body).success,
      ).toBe(false);
    },
  );

  it('normalizes omitted feedback text and rejects bounds or unknown fields', () => {
    expect(
      entryInsightFeedbackRequestSchema.parse({
        verdict: 'accurate',
        correctedStatement: '   ',
        note: '\n',
      }),
    ).toEqual({
      verdict: 'accurate',
      correctedStatement: null,
      note: null,
    });
    expect(
      entryInsightFeedbackRequestSchema.safeParse({
        verdict: 'accurate',
        correctedStatement: 'x'.repeat(reviewCorrectionMaxLength + 1),
      }).success,
    ).toBe(false);
    expect(
      patternFeedbackRequestSchema.safeParse({
        verdict: 'resonates',
        note: 'x'.repeat(reviewNoteMaxLength + 1),
      }).success,
    ).toBe(false);
    expect(
      entryInsightFeedbackRequestSchema.safeParse({
        verdict: 'accurate',
        unexpected: true,
      }).success,
    ).toBe(false);
  });

  it('parses the exact camelCase Entry and Pattern response shapes', () => {
    const response = {
      items: [entryItem(), patternItem()],
      pagination: { page: 1, pageSize: 20, total: 2 },
    };
    expect(reviewItemsResponseSchema.parse(response)).toEqual(response);
  });

  it.each([
    { category: 'self_knowledge' },
    { inferenceLevel: 'synthesized' },
    { confidence: 1.01 },
    { statement: 'x'.repeat(reviewStatementMaxLength + 1) },
    { sourceQuote: 'x'.repeat(reviewSourceQuoteMaxLength + 1) },
    { status: 'confirmed' },
    { sourceEntryIds: [entryId, secondEntryId] },
    { unexpected: true },
  ])('rejects an invalid Entry item mutation: %o', (mutation) => {
    expect(
      reviewItemsResponseSchema.safeParse({
        items: [{ ...entryItem(), ...mutation }],
        pagination: { page: 1, pageSize: 20, total: 1 },
      }).success,
    ).toBe(false);
  });

  it('rejects feedback whose exact verdict and weight mapping disagree', () => {
    const item = patternItem();
    expect(
      reviewItemsResponseSchema.safeParse({
        items: [
          {
            ...item,
            feedback: { ...item.feedback, evidenceWeight: 1 },
          },
        ],
        pagination: { page: 1, pageSize: 20, total: 1 },
      }).success,
    ).toBe(false);
  });
});
