import { z } from 'zod';

export const entryProcessingStatusSchema = z.enum([
  'completed',
  'processing',
  'failed',
]);

export const entriesRequestSchema = z.object({
  page: z.coerce.number().int().min(1),
  page_size: z.coerce.number().int().min(1).max(100),
  search: z.string().trim().optional(),
  processing_status: entryProcessingStatusSchema.optional(),
});

export const entriesApiThemeSchema = z.object({
  key: z.string().trim().min(1),
  name: z.string().trim().min(1),
  color_hex: z.string().regex(/^#[\da-f]{6}$/i),
  tier: z.enum(['primary', 'secondary', 'tertiary']),
});

export const entriesApiItemSchema = z.object({
  id: z.string().trim().min(1),
  input_type: z.enum(['text', 'voice']),
  entry_date: z.iso.datetime(),
  processing_status: z.string().trim().min(1),
  created_at: z.iso.datetime(),
  content_preview: z.string(),
  themes: z.array(entriesApiThemeSchema),
});

export const entriesApiResponseSchema = z.object({
  items: z.array(entriesApiItemSchema),
  total: z.number().int().nonnegative(),
  total_all: z.number().int().nonnegative(),
  page: z.number().int().min(1),
  page_size: z.number().int().min(1).max(100),
});

export type EntriesApiRequest = z.infer<typeof entriesRequestSchema>;
export type EntriesApiItem = z.infer<typeof entriesApiItemSchema>;
export type EntriesApiResponse = z.infer<typeof entriesApiResponseSchema>;
