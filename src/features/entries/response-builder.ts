import type {
  EntriesApiItem,
  EntriesApiRequest,
  EntriesApiResponse,
} from './api-schema';

interface BuildEntriesApiResponseInput extends EntriesApiRequest {
  entries: EntriesApiItem[];
}

export function buildEntriesApiResponse({
  entries,
  page,
  page_size: pageSize,
}: BuildEntriesApiResponseInput): EntriesApiResponse {
  const sortedEntries = [...entries].sort(
    (left, right) =>
      new Date(right.entry_date).getTime() -
      new Date(left.entry_date).getTime(),
  );
  const start = (page - 1) * pageSize;

  return {
    items: sortedEntries.slice(start, start + pageSize),
    total: entries.length,
    page,
    page_size: pageSize,
  };
}
