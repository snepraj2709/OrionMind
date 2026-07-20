import { themeRegistry, type ThemeKey } from '@/config/design-system';
import { entryStatusPresentation, type EntryStatus } from '@/config/status';
import type { EntrySummary } from '@/types/records';

import type { EntriesApiItem } from './api-schema';

function isEntryStatus(value: string): value is EntryStatus {
  return Object.hasOwn(entryStatusPresentation, value);
}

function isThemeKey(value: string): value is ThemeKey {
  return Object.hasOwn(themeRegistry, value);
}

export function mapEntriesApiItem(item: EntriesApiItem): EntrySummary {
  if (!isEntryStatus(item.processing_status)) {
    throw new Error(
      `Unsupported entry processing status: ${item.processing_status}`,
    );
  }

  return {
    id: item.id,
    content: item.content_preview,
    date: item.entry_date,
    inputType: item.input_type,
    status: item.processing_status,
    themes: item.themes.map((theme) => theme.key).filter(isThemeKey),
  };
}
