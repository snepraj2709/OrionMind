import type { EntriesQuery } from './model';

export const entryKeys = {
  all: ['entries'] as const,
  details: ['entries', 'detail'] as const,
  detail: (entryId: string) => ['entries', 'detail', entryId] as const,
  draft: ['entries', 'draft'] as const,
  lists: ['entries', 'list'] as const,
  list: (query: EntriesQuery) => ['entries', 'list', query] as const,
};
