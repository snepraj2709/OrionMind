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
  processing_status: processingStatus,
  search,
}: BuildEntriesApiResponseInput): EntriesApiResponse {
  const normalizedSearch = search?.trim().toLocaleLowerCase() ?? '';
  const sortedEntries = [...entries].sort(
    (left, right) =>
      new Date(right.entry_date).getTime() -
      new Date(left.entry_date).getTime(),
  );
  const matchingEntries = sortedEntries.filter((entry) => {
    const matchesSearch =
      normalizedSearch.length === 0 ||
      entry.content_preview.toLocaleLowerCase().includes(normalizedSearch);
    const matchesStatus =
      processingStatus === undefined ||
      entry.processing_status === processingStatus;

    return matchesSearch && matchesStatus;
  });
  const start = (page - 1) * pageSize;

  return {
    items: matchingEntries.slice(start, start + pageSize),
    total: matchingEntries.length,
    total_all: entries.length,
    page,
    page_size: pageSize,
  };
}
