import { z } from 'zod';

import type { EntryDetail } from '@/types/records';

import fixtureData from './fixtures.json';
import { mapEntriesApiItem } from './adapter';
import { entriesApiItemSchema } from './api-schema';

const extractedItemSchema = z.object({
  id: z.string().min(1),
  content: z.string().min(1),
  kind: z.enum(['idea', 'memory', 'reflection']),
  status: z.enum(['pending_approval', 'approved', 'rejected']),
});

const entryFixtureSchema = entriesApiItemSchema.extend({
  ideas: z.array(extractedItemSchema),
  memories: z.array(extractedItemSchema),
  reflections: z.array(extractedItemSchema),
  processing_error: z.string().min(1).optional(),
});

const fixtureFileSchema = z.object({
  entries: z.array(entryFixtureSchema),
});

export const entryFixtures = fixtureFileSchema.parse(fixtureData).entries;

export const entriesApiFixtures = entryFixtures.map((entry) =>
  entriesApiItemSchema.parse(entry),
);

export const entryDetailFixtures: EntryDetail[] = entryFixtures.map((entry) => {
  const summary = mapEntriesApiItem(entry);

  return {
    ...summary,
    date: entry.entry_date.slice(0, 10),
    ideas: entry.ideas,
    memories: entry.memories,
    reflections: entry.reflections,
    processingError: entry.processing_error,
  };
});
