import { z } from 'zod';

export const reflectionRangeSchema = z.enum(['7d', '30d', 'all']);
export const reflectionRequestSchema = z
  .object({ range: reflectionRangeSchema })
  .strict();

export const reflectionStateSchema = z.enum([
  'available',
  'first_reflection_pending',
  'stale',
  'insufficient_reflective_content',
  'technical_failure',
]);
export const reflectionProcessingStateSchema = z.enum([
  'idle',
  'pending',
  'failed',
]);
export const reflectionFeedbackResponseSchema = z.enum([
  'resonates',
  'partly',
  'rejected',
]);
export const reflectionConfidenceSchema = z.enum([
  'preliminary',
  'emerging',
  'recurring',
]);
export const reflectionReasonCodeSchema = z.enum([
  'NOT_ENOUGH_REFLECTIVE_CONTENT',
  'MINIMUM_BASIS_NOT_MET',
  'DRIVER_NOT_REPEATED',
  'LOOP_NOT_REPEATED',
  'BOTH_SIDES_NOT_SUPPORTED',
  'INSUFFICIENT_EVIDENCE',
]);
export const reflectionSectionStatusSchema = z.enum([
  'available',
  'processing',
  'insufficient_evidence',
  'unavailable',
]);

const themeKeySchema = z.enum([
  'career',
  'money',
  'health',
  'love_life',
  'family_friends',
  'personal_growth',
  'fun_recreation',
  'home_lifestyle',
]);

const needTagSchema = z.enum([
  'autonomy',
  'competence',
  'mastery',
  'belonging',
  'recognition',
  'security',
  'stability',
  'novelty',
  'exploration',
  'meaning',
  'contribution',
  'creative_expression',
  'rest',
  'physical_vitality',
  'clarity',
  'control',
]);

const entryKindSchema = z.enum([
  'personal_reflection',
  'personal_event',
  'personal_observation',
  'task_or_note',
  'informational_text',
  'creative_writing',
  'test_or_noise',
  'copied_or_quoted_text',
  'unclear',
]);

export const evidenceItemSchema = z
  .object({
    id: z.uuid(),
    entryDate: z.iso.date(),
    sourceLabel: z.string().trim().min(1).max(80),
    quote: z.string().trim().min(1).max(4000),
    interpretation: z.string().trim().min(1).max(1000),
    theme: themeKeySchema.nullable(),
    supports: z.string().trim().min(1).max(200),
  })
  .strict();

export const insufficientInsightSchema = z
  .object({
    status: z.literal('insufficient_evidence'),
    reasonCode: reflectionReasonCodeSchema,
    message: z.string().trim().min(1).max(500),
  })
  .strict();

export const processingInsightSchema = z
  .object({
    status: z.literal('processing'),
    message: z.string().trim().min(1).max(500),
  })
  .strict();

export const unavailableInsightSchema = z
  .object({
    status: z.literal('unavailable'),
    reasonCode: z.literal('TECHNICAL_FAILURE'),
    message: z.string().trim().min(1).max(500),
    retryable: z.boolean(),
  })
  .strict();

const availableInsightFields = {
  status: z.literal('available'),
  id: z.uuid(),
  confidence: reflectionConfidenceSchema,
  score: z.number().finite().min(0).max(1),
  evidenceEntryCount: z.number().int().min(1),
  evidence: z.array(evidenceItemSchema),
  feedback: reflectionFeedbackResponseSchema.nullable(),
} as const;

export const availableHiddenDriverSchema = z
  .object({
    ...availableInsightFields,
    statement: z.string().trim().min(1).max(1000),
    underlyingNeed: z.string().trim().min(1).max(200),
    drivers: z.array(z.string().trim().min(1)).max(5),
  })
  .strict();

export const hiddenDriverSectionSchema = z.discriminatedUnion('status', [
  availableHiddenDriverSchema,
  insufficientInsightSchema,
]);

export const recurringLoopStepSchema = z
  .object({
    id: z.uuid(),
    text: z.string().trim().min(1).max(1000),
    evidence: z.array(evidenceItemSchema),
  })
  .strict();

export const availableRecurringLoopSchema = z
  .object({
    ...availableInsightFields,
    title: z.string().trim().min(1).max(300),
    description: z.string().trim().min(1).max(1000),
    steps: z.array(recurringLoopStepSchema).min(3).max(6),
    protection: z.string().trim().min(1).max(1000),
    interruption: z.string().trim().min(1).max(1000),
  })
  .strict();

export const recurringLoopSectionSchema = z.discriminatedUnion('status', [
  availableRecurringLoopSchema,
  insufficientInsightSchema,
]);

export const innerTensionSchema = z
  .object({
    id: z.uuid(),
    confidence: reflectionConfidenceSchema,
    score: z.number().finite().min(0).max(1),
    evidenceEntryCount: z.number().int().min(1),
    leftTitle: needTagSchema,
    leftBody: z.string().trim().min(1).max(1000),
    rightTitle: needTagSchema,
    rightBody: z.string().trim().min(1).max(1000),
    integration: z.string().trim().min(1).max(1000),
    dates: z.array(z.iso.date()),
    evidence: z.array(evidenceItemSchema),
    feedback: reflectionFeedbackResponseSchema.nullable(),
  })
  .strict();

export const availableInnerTensionsSchema = z
  .object({
    status: z.literal('available'),
    tensions: z.array(innerTensionSchema).min(1).max(5),
  })
  .strict();

export const innerTensionsSectionSchema = z.discriminatedUnion('status', [
  availableInnerTensionsSchema,
  insufficientInsightSchema,
]);

export const reflectionSnapshotSchema = z
  .object({
    id: z.uuid(),
    version: z.number().int().min(1),
    generatedAt: z.iso.datetime({ offset: true }),
    sourceVersion: z.number().int().min(1),
    isStale: z.boolean(),
  })
  .strict();

export const reflectionAnalysisBasisSchema = z
  .object({
    window: z.literal('90d'),
    validEntryCount: z.number().int().nonnegative(),
    excludedEntryCount: z.number().int().nonnegative(),
    distinctEntryDates: z.number().int().nonnegative(),
    reflectiveWordCount: z.number().int().nonnegative(),
    currentRangeFrom: z.iso.date().nullable(),
    currentRangeTo: z.iso.date().nullable(),
    excludedReasons: z
      .partialRecord(entryKindSchema, z.number().int().positive())
      .nullable(),
  })
  .strict();

export const reflectionApiResponseSchema = z
  .object({
    range: reflectionRangeSchema,
    reflectionState: reflectionStateSchema,
    processingState: reflectionProcessingStateSchema,
    snapshot: reflectionSnapshotSchema.nullable(),
    analysisBasis: reflectionAnalysisBasisSchema,
    data: z
      .object({
        hiddenDriver: hiddenDriverSectionSchema,
        recurringLoop: recurringLoopSectionSchema,
        innerTensions: innerTensionsSectionSchema,
      })
      .strict(),
  })
  .strict();

export const reflectionFeedbackRequestSchema = z
  .object({ response: reflectionFeedbackResponseSchema })
  .strict();

export const reflectionFeedbackResultSchema = z
  .object({
    snapshotId: z.uuid(),
    insightId: z.uuid(),
    response: reflectionFeedbackResponseSchema,
    updatedAt: z.iso.datetime({ offset: true }),
  })
  .strict();

export type ReflectionRange = z.infer<typeof reflectionRangeSchema>;
export type ReflectionRequest = z.infer<typeof reflectionRequestSchema>;
export type ReflectionSectionStatus = z.infer<
  typeof reflectionSectionStatusSchema
>;
export type ProcessingInsight = z.infer<typeof processingInsightSchema>;
export type UnavailableInsight = z.infer<typeof unavailableInsightSchema>;
export type ReflectionFeedbackResponse = z.infer<
  typeof reflectionFeedbackResponseSchema
>;
export type EvidenceItem = z.infer<typeof evidenceItemSchema>;
export type InsufficientInsight = z.infer<typeof insufficientInsightSchema>;
export type HiddenDriverSection = z.infer<typeof hiddenDriverSectionSchema>;
export type AvailableHiddenDriver = z.infer<typeof availableHiddenDriverSchema>;
export type RecurringLoopStep = z.infer<typeof recurringLoopStepSchema>;
export type RecurringLoopSection = z.infer<typeof recurringLoopSectionSchema>;
export type AvailableRecurringLoop = z.infer<
  typeof availableRecurringLoopSchema
>;
export type InnerTension = z.infer<typeof innerTensionSchema>;
export type InnerTensionsSection = z.infer<typeof innerTensionsSectionSchema>;
export type ReflectionApiResponse = z.infer<typeof reflectionApiResponseSchema>;
export type ReflectionFeedbackResult = z.infer<
  typeof reflectionFeedbackResultSchema
>;
