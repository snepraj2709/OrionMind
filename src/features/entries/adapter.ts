import { themeRegistry, type ThemeKey } from '@/config/design-system';
import { entryStatusPresentation, type EntryStatus } from '@/config/status';
import type { EntrySummary } from '@/types/records';

import type { CreatedEntryApiResponse, EntriesApiItem } from './api-schema';

function isEntryStatus(value: string): value is EntryStatus {
  return Object.hasOwn(entryStatusPresentation, value);
}

function isThemeKey(value: string): value is ThemeKey {
  return Object.hasOwn(themeRegistry, value);
}

const backendThemeKeys = {
  career: 'career',
  money: 'money',
  health: 'health',
  love_life: 'loveLife',
  family_friends: 'familyAndFriends',
  personal_growth: 'personalGrowth',
  fun_recreation: 'funAndRecreation',
  home_lifestyle: 'homeAndLifestyle',
} as const satisfies Record<string, ThemeKey>;

function mapThemeKey(value: string): ThemeKey | null {
  if (isThemeKey(value)) return value;
  return Object.hasOwn(backendThemeKeys, value)
    ? backendThemeKeys[value as keyof typeof backendThemeKeys]
    : null;
}

function mapThemeKeys(values: string[]) {
  return values
    .map(mapThemeKey)
    .filter((value): value is ThemeKey => value !== null);
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
    inputType: item.input_type === 'audio' ? 'voice' : 'text',
    status: item.processing_status,
    themes: mapThemeKeys(item.themes.map((theme) => theme.key)),
  };
}

export function mapCreatedEntryApiResponse(
  item: CreatedEntryApiResponse,
): EntrySummary {
  return {
    id: item.id,
    content: item.content,
    date: item.entry_date,
    inputType: item.input_type === 'audio' ? 'voice' : 'text',
    status: item.processing_status,
    themes: mapThemeKeys(
      item.classification?.themes.map((theme) => theme.key) ?? [],
    ),
  };
}
