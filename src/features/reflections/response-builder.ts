import { deriveReflectionViewModel } from './adapter';
import type {
  ReflectionApiResponse,
  ReflectionRange,
  ReflectionRequest,
} from './api-schema';
import type { JournalEntry } from './model';

export function reflectionEntriesForRange(
  entries: JournalEntry[],
  range: ReflectionRange,
) {
  if (range === 'all' || entries.length === 0) return entries;

  const latestDate = entries.reduce(
    (latest, entry) => (entry.entry_date > latest ? entry.entry_date : latest),
    entries[0]!.entry_date,
  );
  const finalDay = new Date(`${latestDate}T00:00:00Z`);
  const periodDays = range === '7d' ? 7 : 30;
  const firstDay = new Date(finalDay);
  firstDay.setUTCDate(firstDay.getUTCDate() - (periodDays - 1));
  const firstDate = firstDay.toISOString().slice(0, 10);

  return entries.filter((entry) => entry.entry_date >= firstDate);
}

interface BuildReflectionResponseInput extends ReflectionRequest {
  entries: JournalEntry[];
  totalAvailable: number;
}

export function buildReflectionApiResponse({
  entries,
  range,
  reflectionTab,
  totalAvailable,
  userId,
}: BuildReflectionResponseInput): ReflectionApiResponse {
  const filteredEntries = reflectionEntriesForRange(entries, range);
  const viewModel = deriveReflectionViewModel(filteredEntries);
  const envelope = {
    userId,
    range,
    period: {
      entryCount: viewModel.entryCount,
      totalAvailable,
      from: viewModel.from,
      to: viewModel.to,
    },
  } as const;

  switch (reflectionTab) {
    case 'all':
      return {
        ...envelope,
        reflectionTab,
        data: {
          hiddenDriver: viewModel.hiddenDriver,
          recurringLoop: viewModel.loop,
          innerTension: viewModel.innerTension,
        },
      };
    case 'hiddenDriver':
      return {
        ...envelope,
        reflectionTab,
        data: viewModel.hiddenDriver,
      };
    case 'recurringLoop':
      return {
        ...envelope,
        reflectionTab,
        data: viewModel.loop,
      };
    case 'innerTension':
      return {
        ...envelope,
        reflectionTab,
        data: viewModel.innerTension,
      };
  }
}
