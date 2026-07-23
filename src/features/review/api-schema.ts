import { z } from 'zod';

export const reviewScopeSchema = z.enum(['entry_insight', 'pattern']);
export const entryInsightTypeSchema = z.enum([
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
export const patternTypeSchema = z.enum([
  'hidden_driver',
  'recurring_loop',
  'inner_tension',
]);
export const entryInsightCategorySchema = z.enum([
  'energy',
  'self_knowledge',
  'needs_beliefs',
]);
export const patternCategorySchema = z.enum([
  'hidden_driver',
  'recurring_loop',
  'inner_tension',
]);
export const reviewCategoryFilterSchema = z.enum([
  'all',
  ...entryInsightCategorySchema.options,
  ...patternCategorySchema.options,
]);
export const reviewStatusSchema = z.enum([
  'pending',
  'confirmed',
  'partially_confirmed',
  'rejected',
]);
export const inferenceLevelSchema = z.enum([
  'direct',
  'inferred',
  'synthesized',
]);
export const entryInsightVerdictSchema = z.enum([
  'accurate',
  'partly_accurate',
  'not_accurate',
]);
export const patternVerdictSchema = z.enum([
  'resonates',
  'partly_true',
  'not_true',
]);
export const reviewVerdictSchema = z.union([
  entryInsightVerdictSchema,
  patternVerdictSchema,
]);

export const reviewPageSizeDefault = 20;
export const reviewPageSizeMax = 100;
export const reviewStatementMaxLength = 1000;
export const reviewSourceQuoteMaxLength = 4000;
export const reviewCorrectionMaxLength = 1000;
export const reviewNoteMaxLength = 1000;

const entryInsightCategoryByType = {
  energy_gain: 'energy',
  energy_loss: 'energy',
  self_knowledge: 'self_knowledge',
  realization: 'self_knowledge',
  explicit_preference: 'self_knowledge',
  need: 'needs_beliefs',
  belief: 'needs_beliefs',
  avoidance: 'needs_beliefs',
  protective_strategy: 'needs_beliefs',
  conflict: 'needs_beliefs',
  causal_relationship: 'needs_beliefs',
} as const;

const patternCategoryByType = {
  hidden_driver: 'hidden_driver',
  recurring_loop: 'recurring_loop',
  inner_tension: 'inner_tension',
} as const;

const entryInsightStatusByVerdict = {
  accurate: 'confirmed',
  partly_accurate: 'partially_confirmed',
  not_accurate: 'rejected',
} as const;

const patternStatusByVerdict = {
  resonates: 'confirmed',
  partly_true: 'partially_confirmed',
  not_true: 'rejected',
} as const;

const optionalFeedbackText = (maximum: number) =>
  z
    .preprocess(
      (value) =>
        typeof value === 'string' && value.trim() === '' ? null : value,
      z.string().trim().min(1).max(maximum).nullable(),
    )
    .default(null);

export const reviewListQuerySchema = z
  .object({
    scope: reviewScopeSchema,
    category: reviewCategoryFilterSchema.default('all'),
    status: reviewStatusSchema.default('pending'),
    page: z.number().int().min(1).default(1),
    page_size: z
      .number()
      .int()
      .min(1)
      .max(reviewPageSizeMax)
      .default(reviewPageSizeDefault),
  })
  .strict()
  .superRefine((value, context) => {
    if (
      value.category !== 'all' &&
      value.scope === 'entry_insight' &&
      !entryInsightCategorySchema.safeParse(value.category).success
    ) {
      context.addIssue({
        code: 'custom',
        message: 'category is not valid for the selected scope',
        path: ['category'],
      });
    }
    if (
      value.category !== 'all' &&
      value.scope === 'pattern' &&
      !patternCategorySchema.safeParse(value.category).success
    ) {
      context.addIssue({
        code: 'custom',
        message: 'category is not valid for the selected scope',
        path: ['category'],
      });
    }
  });

const feedbackRequestFields = {
  correctedStatement: optionalFeedbackText(reviewCorrectionMaxLength),
  note: optionalFeedbackText(reviewNoteMaxLength),
} as const;

export const entryInsightFeedbackRequestSchema = z
  .object({
    verdict: entryInsightVerdictSchema,
    ...feedbackRequestFields,
  })
  .strict();

export const patternFeedbackRequestSchema = z
  .object({
    verdict: patternVerdictSchema,
    ...feedbackRequestFields,
  })
  .strict();

export const reviewFeedbackRequestSchema = z.union([
  entryInsightFeedbackRequestSchema,
  patternFeedbackRequestSchema,
]);

export function feedbackRequestSchemaForScope(scope: ReviewScope) {
  return scope === 'entry_insight'
    ? entryInsightFeedbackRequestSchema
    : patternFeedbackRequestSchema;
}

const feedbackResponseFields = {
  correctedStatement: optionalFeedbackText(reviewCorrectionMaxLength),
  note: optionalFeedbackText(reviewNoteMaxLength),
  updatedAt: z.iso.datetime({ offset: true }),
} as const;

export const entryInsightFeedbackSchema = z.discriminatedUnion('verdict', [
  z
    .object({
      verdict: z.literal('accurate'),
      evidenceWeight: z.literal(1),
      ...feedbackResponseFields,
    })
    .strict(),
  z
    .object({
      verdict: z.literal('partly_accurate'),
      evidenceWeight: z.literal(0.5),
      ...feedbackResponseFields,
    })
    .strict(),
  z
    .object({
      verdict: z.literal('not_accurate'),
      evidenceWeight: z.literal(0),
      ...feedbackResponseFields,
    })
    .strict(),
]);

export const patternFeedbackSchema = z.discriminatedUnion('verdict', [
  z
    .object({
      verdict: z.literal('resonates'),
      evidenceWeight: z.literal(1),
      ...feedbackResponseFields,
    })
    .strict(),
  z
    .object({
      verdict: z.literal('partly_true'),
      evidenceWeight: z.literal(0.5),
      ...feedbackResponseFields,
    })
    .strict(),
  z
    .object({
      verdict: z.literal('not_true'),
      evidenceWeight: z.literal(0),
      ...feedbackResponseFields,
    })
    .strict(),
]);

const uniqueArray = <T extends z.ZodType>(item: T, maximum: number) =>
  z
    .array(item)
    .min(1)
    .max(maximum)
    .refine((values) => new Set(values).size === values.length, {
      message: 'values must be distinct',
    });

const reviewItemBaseFields = {
  id: z.uuid(),
  statement: z.string().trim().min(1).max(reviewStatementMaxLength),
  confidence: z.number().finite().min(0).max(1),
  status: reviewStatusSchema,
} as const;

const entryInsightReviewItemSchema = z
  .object({
    ...reviewItemBaseFields,
    scope: z.literal('entry_insight'),
    type: entryInsightTypeSchema,
    category: entryInsightCategorySchema,
    sourceQuote: z
      .string()
      .trim()
      .min(1)
      .max(reviewSourceQuoteMaxLength)
      .nullable(),
    sourceEntryIds: uniqueArray(z.uuid(), 1),
    sourceDates: uniqueArray(z.iso.date(), 1),
    inferenceLevel: z.enum(['direct', 'inferred']),
    feedback: entryInsightFeedbackSchema.nullable(),
  })
  .strict();

const patternReviewItemSchema = z
  .object({
    ...reviewItemBaseFields,
    scope: z.literal('pattern'),
    type: patternTypeSchema,
    category: patternCategorySchema,
    sourceQuote: z.null(),
    sourceEntryIds: uniqueArray(z.uuid(), 100),
    sourceDates: uniqueArray(z.iso.date(), 100),
    inferenceLevel: z.literal('synthesized'),
    feedback: patternFeedbackSchema.nullable(),
  })
  .strict();

export const reviewItemSchema = z
  .discriminatedUnion('scope', [
    entryInsightReviewItemSchema,
    patternReviewItemSchema,
  ])
  .superRefine((value, context) => {
    const expectedCategory =
      value.scope === 'entry_insight'
        ? entryInsightCategoryByType[value.type]
        : patternCategoryByType[value.type];
    if (value.category !== expectedCategory) {
      context.addIssue({
        code: 'custom',
        message: 'category does not match the item type',
        path: ['category'],
      });
    }

    const expectedStatus =
      value.feedback === null
        ? 'pending'
        : value.scope === 'entry_insight'
          ? entryInsightStatusByVerdict[value.feedback.verdict]
          : patternStatusByVerdict[value.feedback.verdict];
    if (value.status !== expectedStatus) {
      context.addIssue({
        code: 'custom',
        message: 'review status does not match feedback',
        path: ['status'],
      });
    }
  });

export const reviewPaginationSchema = z
  .object({
    page: z.number().int().min(1),
    pageSize: z.number().int().min(1).max(reviewPageSizeMax),
    total: z.number().int().nonnegative(),
  })
  .strict();

export const reviewItemsResponseSchema = z
  .object({
    items: z.array(reviewItemSchema).max(reviewPageSizeMax),
    pagination: reviewPaginationSchema,
  })
  .strict();

export type ReviewScope = z.infer<typeof reviewScopeSchema>;
export type EntryInsightType = z.infer<typeof entryInsightTypeSchema>;
export type PatternType = z.infer<typeof patternTypeSchema>;
export type EntryInsightCategory = z.infer<typeof entryInsightCategorySchema>;
export type PatternCategory = z.infer<typeof patternCategorySchema>;
export type ReviewCategoryFilter = z.infer<typeof reviewCategoryFilterSchema>;
export type ReviewStatus = z.infer<typeof reviewStatusSchema>;
export type InferenceLevel = z.infer<typeof inferenceLevelSchema>;
export type EntryInsightVerdict = z.infer<typeof entryInsightVerdictSchema>;
export type PatternVerdict = z.infer<typeof patternVerdictSchema>;
export type ReviewVerdict = z.infer<typeof reviewVerdictSchema>;
export type ReviewListQuery = z.infer<typeof reviewListQuerySchema>;
export type ReviewFeedbackRequest = z.infer<typeof reviewFeedbackRequestSchema>;
export type EntryInsightFeedback = z.infer<typeof entryInsightFeedbackSchema>;
export type PatternFeedback = z.infer<typeof patternFeedbackSchema>;
export type ReviewItem = z.infer<typeof reviewItemSchema>;
export type ReviewItemsResponse = z.infer<typeof reviewItemsResponseSchema>;
