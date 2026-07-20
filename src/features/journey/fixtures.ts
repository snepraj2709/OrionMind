import type { ThemeKey } from '@/config/design-system';

import type {
  EntryTheme,
  JourneyEntry,
  JourneyRange,
  JourneyStatusResponse,
  JourneySteamPoint,
} from './model';

const themeCycles: EntryTheme[][] = [
  [
    { rank: 'primary', value: 'career' },
    { rank: 'secondary', value: 'personal_growth' },
    { rank: 'tertiary', value: 'money' },
  ],
  [
    { rank: 'primary', value: 'personal_growth' },
    { rank: 'secondary', value: 'career' },
    { rank: 'tertiary', value: 'health' },
  ],
  [
    { rank: 'primary', value: 'love_life' },
    { rank: 'secondary', value: 'home_lifestyle' },
    { rank: 'tertiary', value: 'family_friends' },
  ],
  [
    { rank: 'primary', value: 'health' },
    { rank: 'secondary', value: 'personal_growth' },
    { rank: 'tertiary', value: 'fun_recreation' },
  ],
];

export const journeyEntryFixtures: JourneyEntry[] = Array.from(
  { length: 30 },
  (_, index) => {
    const date = new Date(Date.UTC(2023, 8 + index, 5));
    return {
      entry_date: date.toISOString().slice(0, 10),
      theme: themeCycles[Math.floor(index / 8) % themeCycles.length]!,
      content: {
        added_energy: [
          `A small step during month ${index + 1} made the direction feel more visible.`,
        ],
        drained_energy: [
          `Competing responsibilities during month ${index + 1} reduced the space available to recover.`,
        ],
        self_knowledge: [
          `I was beginning to understand what I wanted to carry forward from month ${index + 1}.`,
        ],
      },
    };
  },
);

export const journeyStatusFixture: JourneyStatusResponse = {
  enabled: false,
  daysSinceSignup: 18,
  entriesAdded: 9,
};

function themeValues(
  values: Partial<Record<ThemeKey, number>>,
): Record<ThemeKey, number> {
  return {
    career: 0,
    money: 0,
    health: 0,
    loveLife: 0,
    familyAndFriends: 0,
    personalGrowth: 0,
    funAndRecreation: 0,
    homeAndLifestyle: 0,
    ...values,
  };
}

const steamValues: Array<Record<ThemeKey, number>> = [
  themeValues({
    career: 0.8,
    money: 0.1,
    health: 0.15,
    loveLife: 0.1,
    familyAndFriends: 0.05,
    personalGrowth: 0.7,
    funAndRecreation: 0.1,
    homeAndLifestyle: 0.2,
  }),
  themeValues({
    career: 0.9,
    money: 0.1,
    health: 0.05,
    loveLife: 0.1,
    familyAndFriends: 0.05,
    personalGrowth: 0.9,
    funAndRecreation: 0.75,
    homeAndLifestyle: 0.15,
  }),
  themeValues({
    career: 0.3,
    money: 0.1,
    health: 0.05,
    loveLife: 0.9,
    familyAndFriends: 0.55,
    personalGrowth: 0.15,
    funAndRecreation: 0.1,
    homeAndLifestyle: 0.2,
  }),
  themeValues({
    career: 0.25,
    money: 0.15,
    health: 0.1,
    loveLife: 1,
    familyAndFriends: 0.1,
    personalGrowth: 0.7,
    funAndRecreation: 0.1,
    homeAndLifestyle: 0.9,
  }),
  themeValues({
    career: 0.65,
    money: 0.1,
    health: 0.9,
    loveLife: 0.6,
    familyAndFriends: 0.1,
    personalGrowth: 0.3,
    funAndRecreation: 0.1,
    homeAndLifestyle: 0.95,
  }),
  themeValues({
    career: 0.9,
    money: 0.1,
    health: 0.15,
    loveLife: 0.3,
    familyAndFriends: 0.15,
    personalGrowth: 0.75,
    funAndRecreation: 0.5,
    homeAndLifestyle: 0.2,
  }),
];

const rangeDates: Record<
  JourneyRange,
  Array<{ date: string; label: string }>
> = {
  '6m': [
    { date: '2024-02-01', label: 'Feb 2024' },
    { date: '2024-03-01', label: 'Mar 2024' },
    { date: '2024-04-01', label: 'Apr 2024' },
    { date: '2024-05-01', label: 'May 2024' },
    { date: '2024-06-01', label: 'Jun 2024' },
    { date: '2024-07-01', label: 'Jul 2024' },
  ],
  '1y': [
    { date: '2023-09-01', label: 'Sep 2023' },
    { date: '2023-11-01', label: 'Nov 2023' },
    { date: '2024-01-01', label: 'Jan 2024' },
    { date: '2024-03-01', label: 'Mar 2024' },
    { date: '2024-05-01', label: 'May 2024' },
    { date: '2024-07-01', label: 'Jul 2024' },
  ],
  '2y': [
    { date: '2022-09-01', label: 'Sep 2022' },
    { date: '2023-01-01', label: 'Jan 2023' },
    { date: '2023-05-01', label: 'May 2023' },
    { date: '2023-09-01', label: 'Sep 2023' },
    { date: '2024-01-01', label: 'Jan 2024' },
    { date: '2024-07-01', label: 'Jul 2024' },
  ],
  '3y': [
    { date: '2021-09-01', label: 'Sep 2021' },
    { date: '2022-03-01', label: 'Mar 2022' },
    { date: '2022-09-01', label: 'Sep 2022' },
    { date: '2023-03-01', label: 'Mar 2023' },
    { date: '2023-09-01', label: 'Sep 2023' },
    { date: '2024-07-01', label: 'Jul 2024' },
  ],
  '5y': [
    { date: '2019-09-01', label: 'Sep 2019' },
    { date: '2020-09-01', label: 'Sep 2020' },
    { date: '2021-09-01', label: 'Sep 2021' },
    { date: '2022-09-01', label: 'Sep 2022' },
    { date: '2023-09-01', label: 'Sep 2023' },
    { date: '2024-07-01', label: 'Jul 2024' },
  ],
  all: [
    { date: '2023-09-01', label: 'Sep 2023' },
    { date: '2023-11-01', label: 'Nov 2023' },
    { date: '2024-01-01', label: 'Jan 2024' },
    { date: '2024-03-01', label: 'Mar 2024' },
    { date: '2024-05-01', label: 'May 2024' },
    { date: '2024-07-01', label: 'Jul 2024' },
  ],
};

export const journeyStreamFixtures = Object.fromEntries(
  Object.entries(rangeDates).map(([range, dates]) => [
    range,
    dates.map<JourneySteamPoint>((date, index) => ({
      ...date,
      values: { ...steamValues[index]! },
    })),
  ]),
) as Record<JourneyRange, JourneySteamPoint[]>;

export function journeyStreamForRange(range: JourneyRange) {
  return journeyStreamFixtures[range].map((point) => ({
    ...point,
    values: { ...point.values },
  }));
}

export function cloneJourneyEntries(entries: JourneyEntry[]) {
  return entries.map((entry) => ({
    entry_date: entry.entry_date,
    theme: entry.theme.map((theme) => ({ ...theme })),
    content: {
      added_energy: [...entry.content.added_energy],
      drained_energy: [...entry.content.drained_energy],
      self_knowledge: [...entry.content.self_knowledge],
    },
  }));
}

export function journeyEntriesForRange(
  entries: JourneyEntry[],
  range: JourneyRange,
) {
  if (range === 'all' || entries.length === 0)
    return cloneJourneyEntries(entries);

  const periodMonths: Record<Exclude<JourneyRange, 'all'>, number> = {
    '6m': 6,
    '1y': 12,
    '2y': 24,
    '3y': 36,
    '5y': 60,
  };
  const finalDate = new Date(`${entries.at(-1)!.entry_date}T00:00:00Z`);
  finalDate.setUTCMonth(finalDate.getUTCMonth() - (periodMonths[range] - 1));
  const firstDate = finalDate.toISOString().slice(0, 10);
  return cloneJourneyEntries(
    entries.filter((entry) => entry.entry_date >= firstDate),
  );
}
