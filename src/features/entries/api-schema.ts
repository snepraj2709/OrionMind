import { z } from 'zod';

export const entryProcessingStatusSchema = z.enum([
  'pending',
  'completed',
  'processing',
  'failed',
]);

export const entriesRequestSchema = z.object({
  page: z.coerce.number().int().min(1),
  page_size: z.coerce.number().int().min(1).max(100),
});

export const entriesApiThemeSchema = z.object({
  key: z.string().trim().min(1),
  name: z.string().trim().min(1),
  color_hex: z.string().regex(/^#[\da-f]{6}$/i),
  tier: z.enum(['primary', 'secondary', 'tertiary']),
});

export const entriesApiItemSchema = z.object({
  id: z.string().trim().min(1),
  input_type: z.enum(['text', 'audio']),
  entry_date: z.iso.date(),
  processing_status: entryProcessingStatusSchema,
  created_at: z.iso.datetime(),
  content_preview: z.string(),
  themes: z.array(entriesApiThemeSchema),
});

export const entriesApiResponseSchema = z.object({
  items: z.array(entriesApiItemSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().min(1),
  page_size: z.number().int().min(1).max(100),
});

export const entryDraftApiResponseSchema = z.object({
  content: z.string().nullable(),
  updated_at: z.iso.datetime().nullable(),
});

const createdEntryThemeSchema = z.object({
  key: z.string().trim().min(1),
  name: z.string().trim().min(1),
  score: z.number().min(0).max(1),
  tier: z.enum(['primary', 'secondary', 'tertiary']),
});

const entryCandidateApiSchema = z.object({
  id: z.uuid(),
  content: z.string(),
  status: z.enum(['pending_approval', 'approved', 'rejected']),
  entry_id: z.uuid(),
  entry_date: z.iso.date(),
  created_at: z.iso.datetime(),
  decided_at: z.iso.datetime().nullable(),
});

const entryReflectionApiSchema = z.object({
  id: z.uuid(),
  reflection_type: z.enum([
    'filled_energy',
    'drained_energy',
    'learned_about_self',
  ]),
  activity: z.string(),
  confidence_score: z.number().min(0).max(1),
  status: z.enum(['pending_approval', 'approved', 'rejected']),
  entry_id: z.uuid(),
  entry_date: z.iso.date(),
  created_at: z.iso.datetime(),
  decided_at: z.iso.datetime().nullable(),
});

// PostgreSQL/Python UUIDs allow fixed identifiers without RFC version bits.
const databaseUuidSchema = z
  .string()
  .regex(/^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i);

const entryClassificationApiSchema = z.object({
  theme_config_id: databaseUuidSchema,
  source: z.enum(['initial', 'backfill']),
  mode: z.enum(['dominant', 'balanced']).nullable(),
  themes: z.array(createdEntryThemeSchema).max(3),
});

export const entryDetailApiResponseSchema = z.object({
  id: z.uuid(),
  content: z.string(),
  input_type: z.enum(['text', 'audio']),
  entry_date: z.iso.date(),
  original_theme_config_id: databaseUuidSchema,
  processing_status: entryProcessingStatusSchema,
  processing_error_code: z.string().nullable(),
  created_at: z.iso.datetime(),
  classification: entryClassificationApiSchema.nullable(),
  ideas: z.array(entryCandidateApiSchema),
  extracted_memories: z.array(entryCandidateApiSchema),
  reflections: z.array(entryReflectionApiSchema),
});

export const createdEntryApiResponseSchema = z.object({
  id: z.uuid(),
  content: z.string(),
  input_type: z.enum(['text', 'audio']),
  entry_date: z.iso.date(),
  processing_status: entryProcessingStatusSchema,
  classification: z
    .object({ themes: z.array(createdEntryThemeSchema).max(3) })
    .nullable(),
});

export type EntriesApiRequest = z.infer<typeof entriesRequestSchema>;
export type EntriesApiItem = z.infer<typeof entriesApiItemSchema>;
export type EntriesApiResponse = z.infer<typeof entriesApiResponseSchema>;
export type EntryDraftApiResponse = z.infer<typeof entryDraftApiResponseSchema>;
export type EntryDetailApiResponse = z.infer<
  typeof entryDetailApiResponseSchema
>;
export type CreatedEntryApiResponse = z.infer<
  typeof createdEntryApiResponseSchema
>;
