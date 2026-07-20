import { z } from 'zod';

export const reflectionTabSchema = z.enum([
  'all',
  'hiddenDriver',
  'innerTension',
  'recurringLoop',
]);

export const reflectionRangeSchema = z.enum(['7d', '30d', 'all']);

export const reflectionRequestSchema = z.object({
  userId: z.string().trim().min(1),
  reflectionTab: reflectionTabSchema,
  range: reflectionRangeSchema,
});

const themeKeySchema = z.enum([
  'career',
  'money',
  'health',
  'loveLife',
  'familyAndFriends',
  'personalGrowth',
  'funAndRecreation',
  'homeAndLifestyle',
]);

export const evidenceItemSchema = z.object({
  id: z.string().min(1),
  date: z.iso.date(),
  source: z.string().min(1),
  text: z.string().min(1),
  interpretation: z.string().min(1).optional(),
  theme: themeKeySchema.optional(),
  rank: z.enum(['primary', 'secondary', 'tertiary']).optional(),
  supports: z.string().min(1).optional(),
});

export const hiddenDriverDataSchema = z.object({
  statement: z.string().min(1),
  underlyingNeed: z.string().min(1),
  drivers: z.array(z.string().min(1)),
  evidenceStrength: z.array(z.string().min(1)),
  observedEntryCount: z.number().int().nonnegative(),
  evidence: z.array(evidenceItemSchema),
});

export const recurringLoopStepSchema = z.object({
  id: z.string().min(1),
  text: z.string().min(1),
  entryCount: z.number().int().nonnegative(),
  evidence: z.array(evidenceItemSchema),
});

export const recurringLoopDataSchema = z.object({
  title: z.string().min(1),
  description: z.string().min(1),
  steps: z.array(recurringLoopStepSchema),
  protection: z.string().min(1),
  interruption: z.string().min(1),
  evidence: z.array(evidenceItemSchema),
});

export const innerTensionItemSchema = z.object({
  id: z.string().min(1),
  leftTitle: z.string().min(1),
  leftBody: z.string().min(1),
  rightTitle: z.string().min(1),
  rightBody: z.string().min(1),
  integration: z.string().min(1),
  dates: z.array(z.iso.date()),
  evidence: z.array(evidenceItemSchema),
});

export const innerTensionDataSchema = z.object({
  title: z.string().min(1),
  tensions: z.array(innerTensionItemSchema),
});

export const reflectionPeriodSchema = z.object({
  entryCount: z.number().int().nonnegative(),
  totalAvailable: z.number().int().nonnegative(),
  from: z.iso.date().nullable(),
  to: z.iso.date().nullable(),
});

const envelopeSchema = z.object({
  userId: z.string().min(1),
  range: reflectionRangeSchema,
  period: reflectionPeriodSchema,
});

export const reflectionApiResponseSchema = z.discriminatedUnion(
  'reflectionTab',
  [
    envelopeSchema.extend({
      reflectionTab: z.literal('all'),
      data: z.object({
        hiddenDriver: hiddenDriverDataSchema,
        innerTension: innerTensionDataSchema,
        recurringLoop: recurringLoopDataSchema,
      }),
    }),
    envelopeSchema.extend({
      reflectionTab: z.literal('hiddenDriver'),
      data: hiddenDriverDataSchema,
    }),
    envelopeSchema.extend({
      reflectionTab: z.literal('innerTension'),
      data: innerTensionDataSchema,
    }),
    envelopeSchema.extend({
      reflectionTab: z.literal('recurringLoop'),
      data: recurringLoopDataSchema,
    }),
  ],
);

export type ReflectionTab = z.infer<typeof reflectionTabSchema>;
export type ReflectionRange = z.infer<typeof reflectionRangeSchema>;
export type ReflectionRequest = z.infer<typeof reflectionRequestSchema>;
export type HiddenDriverData = z.infer<typeof hiddenDriverDataSchema>;
export type RecurringLoopStep = z.infer<typeof recurringLoopStepSchema>;
export type RecurringLoopData = z.infer<typeof recurringLoopDataSchema>;
export type InnerTension = z.infer<typeof innerTensionItemSchema>;
export type InnerTensionData = z.infer<typeof innerTensionDataSchema>;
export type ReflectionPeriod = z.infer<typeof reflectionPeriodSchema>;
export type ReflectionApiResponse = z.infer<typeof reflectionApiResponseSchema>;
