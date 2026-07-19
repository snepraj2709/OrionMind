import { themeRegistry, type ThemeKey } from '@/config/design-system';
import type { EvidenceItem } from '@/types/evidence';

import type {
  JourneyChapter,
  JourneyEntry,
  JourneyRange,
  JourneyViewModel,
  ThemeRank,
  ThemeRiverPoint,
  ThemeValue,
} from './model';

const themeKeys = Object.keys(themeRegistry) as ThemeKey[];
const themeValueToKey: Record<ThemeValue, ThemeKey> = {
  career: 'career',
  money: 'money',
  health: 'health',
  love_life: 'loveLife',
  family_friends: 'familyAndFriends',
  personal_growth: 'personalGrowth',
  fun_recreation: 'funAndRecreation',
  home_lifestyle: 'homeAndLifestyle',
};
const rankWeights: Record<ThemeRank, number> = {
  primary: 1,
  secondary: 0.6,
  tertiary: 0.3,
};
const weekMilliseconds = 7 * 24 * 60 * 60 * 1000;
const weekEpoch = Date.UTC(1970, 0, 5);

type BucketResolution = 'week' | 'biweek' | 'month' | 'quarter';

function emptyThemeValues() {
  return Object.fromEntries(themeKeys.map((key) => [key, 0])) as Record<
    ThemeKey,
    number
  >;
}

function mappedThemes(entry: JourneyEntry) {
  return entry.theme.map((theme) => ({
    key: themeValueToKey[theme.value],
    rank: theme.rank,
  }));
}

function primaryTheme(entry: JourneyEntry) {
  const primary = entry.theme.find((theme) => theme.rank === 'primary');
  return primary ? themeValueToKey[primary.value] : undefined;
}

function themeTotals(entries: JourneyEntry[]) {
  const totals = emptyThemeValues();
  entries.forEach((entry) => {
    mappedThemes(entry).forEach((theme) => {
      totals[theme.key] += rankWeights[theme.rank];
    });
  });
  return totals;
}

function rankedThemes(entries: JourneyEntry[]) {
  const totals = themeTotals(entries);
  return themeKeys
    .filter((key) => totals[key] > 0)
    .sort((left, right) => totals[right] - totals[left]);
}

function joinThemeLabels(keys: ThemeKey[]) {
  const labels = keys.map((key) => themeRegistry[key].label);
  if (labels.length < 2) return labels[0] ?? 'several life themes';
  return `${labels.slice(0, -1).join(', ')} and ${labels.at(-1)}`;
}

function evidenceFrom(
  entries: JourneyEntry[],
  supports: string,
  limit = 12,
): EvidenceItem[] {
  return entries
    .flatMap((entry, entryIndex) => {
      const themes = mappedThemes(entry);
      const categories = [
        ['Added Energy', entry.content.added_energy],
        ['Drained Energy', entry.content.drained_energy],
        ['Self-Knowledge', entry.content.self_knowledge],
      ] as const;

      return categories.flatMap(([source, statements], categoryIndex) => {
        const assignedTheme = themes[categoryIndex] ?? themes[0];
        return statements.map((text, statementIndex) => ({
          id: `${entry.entry_date}-${entryIndex}-${categoryIndex}-${statementIndex}`,
          date: entry.entry_date,
          interpretation:
            'Orion keeps this source sentence separate from the longitudinal interpretation it supports.',
          rank: assignedTheme?.rank,
          source,
          supports,
          text,
          theme: assignedTheme?.key,
        }));
      });
    })
    .filter((item) => item.text)
    .slice(0, limit);
}

function bucketResolution(
  range: JourneyRange,
  entries: JourneyEntry[],
): BucketResolution {
  if (range === '6m') return 'week';
  if (range === '1y') return 'biweek';
  if (range !== 'all') return 'month';

  const first = new Date(`${entries[0]?.entry_date ?? ''}T00:00:00Z`);
  const last = new Date(`${entries.at(-1)?.entry_date ?? ''}T00:00:00Z`);
  const years =
    (last.getTime() - first.getTime()) / (365 * 24 * 60 * 60 * 1000);
  return years > 5 ? 'quarter' : 'month';
}

function bucketForDate(dateValue: string, resolution: BucketResolution) {
  const date = new Date(`${dateValue}T00:00:00Z`);
  if (resolution === 'week' || resolution === 'biweek') {
    const week = Math.floor((date.getTime() - weekEpoch) / weekMilliseconds);
    const bucketWeek =
      resolution === 'biweek' ? Math.floor(week / 2) * 2 : week;
    return new Date(weekEpoch + bucketWeek * weekMilliseconds)
      .toISOString()
      .slice(0, 10);
  }

  const month =
    resolution === 'quarter'
      ? Math.floor(date.getUTCMonth() / 3) * 3
      : date.getUTCMonth();
  return new Date(Date.UTC(date.getUTCFullYear(), month, 1))
    .toISOString()
    .slice(0, 10);
}

function normalizeValues(values: Record<ThemeKey, number>) {
  const total = Object.values(values).reduce((sum, value) => sum + value, 0);
  if (total === 0) return values;
  themeKeys.forEach((key) => {
    values[key] /= total;
  });
  return values;
}

function buildStreamData(entries: JourneyEntry[], range: JourneyRange) {
  const resolution = bucketResolution(range, entries);
  const buckets = new Map<string, JourneyEntry[]>();
  entries.forEach((entry) => {
    const bucket = bucketForDate(entry.entry_date, resolution);
    buckets.set(bucket, [...(buckets.get(bucket) ?? []), entry]);
  });

  const points = [...buckets.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([bucket, bucketEntries], index, allBuckets) => {
      const values = themeTotals(bucketEntries);
      themeKeys.forEach((key) => {
        values[key] /= bucketEntries.length;
      });
      normalizeValues(values);
      const previousEntries =
        index > 0 ? (allBuckets[index - 1]?.[1] ?? []) : [];
      const previousValues = normalizeValues(themeTotals(previousEntries));
      const rising = themeKeys.filter(
        (key) => values[key] - previousValues[key] >= 0.08,
      );
      const fading = themeKeys.filter(
        (key) => previousValues[key] - values[key] >= 0.08,
      );
      const representativeSentence =
        bucketEntries.find((entry) => entry.content.self_knowledge[0])?.content
          .self_knowledge[0] ??
        bucketEntries.find((entry) => entry.content.added_energy[0])?.content
          .added_energy[0] ??
        'No representative sentence is available for this period.';

      return {
        bucket,
        entryCount: bucketEntries.length,
        fading,
        representativeSentence,
        rising,
        values,
      } satisfies ThemeRiverPoint;
    });

  if (range !== '5y') return points;
  return points.map((point, index) => {
    const window = points.slice(Math.max(0, index - 1), index + 2);
    const values = emptyThemeValues();
    window.forEach((windowPoint) => {
      themeKeys.forEach((key) => {
        values[key] += windowPoint.values[key] / window.length;
      });
    });
    return { ...point, values: normalizeValues(values) };
  });
}

function chapterSegments(entries: JourneyEntry[]) {
  const themedEntries = entries.filter((entry) => primaryTheme(entry));
  if (themedEntries.length < 5) return [];
  const runs: JourneyEntry[][] = [];
  themedEntries.forEach((entry) => {
    const nextTheme = primaryTheme(entry);
    const currentRun = runs.at(-1);
    if (!currentRun || primaryTheme(currentRun[0]!) !== nextTheme) {
      runs.push([entry]);
    } else {
      currentRun.push(entry);
    }
  });

  const segments: JourneyEntry[][] = [];
  runs.forEach((run, index) => {
    if (run.length < 5 && index < runs.length - 1) {
      runs[index + 1] = [...run, ...runs[index + 1]!];
    } else if (run.length < 5 && segments.length > 0) {
      segments.at(-1)!.push(...run);
    } else {
      segments.push(run);
    }
  });
  return segments;
}

function chapterThemeDirections(entries: JourneyEntry[]) {
  const midpoint = Math.max(1, Math.floor(entries.length / 2));
  const earlier = themeTotals(entries.slice(0, midpoint));
  const later = themeTotals(entries.slice(midpoint));
  const themes = rankedThemes(entries).slice(0, 3);
  return themes.map((key, index) => {
    const delta = later[key] - earlier[key];
    return {
      direction:
        delta > 0.5
          ? ('rising' as const)
          : delta < -0.5
            ? ('fading' as const)
            : ('stable' as const),
      key,
      rank: (['primary', 'secondary', 'tertiary'] as const)[index]!,
    };
  });
}

function makeChapter(
  entries: JourneyEntry[],
  index: number,
  segmentCount: number,
  previousChapter?: JourneyChapter,
): JourneyChapter {
  const first = entries[0]!;
  const last = entries.at(-1)!;
  const status =
    index === segmentCount - 1
      ? entries.length < 5
        ? ('emerging' as const)
        : ('current' as const)
      : ('completed' as const);
  const themes = chapterThemeDirections(entries);
  const themeLabels = themes.map((theme) => themeRegistry[theme.key].label);
  const primaryLabel = themeLabels[0] ?? 'Change';
  const secondaryLabel = themeLabels[1] ?? 'Continuity';
  const title =
    status === 'emerging'
      ? `An Emerging ${primaryLabel} Chapter`
      : `${primaryLabel} and ${secondaryLabel}`;
  const evidence = evidenceFrom(entries, `${title} chapter interpretation`);
  const dateRange = `${first.entry_date}–${last.entry_date}`;
  const detectionReasons = [
    `${primaryLabel} remained prominent across this period.`,
    `The relative theme mix differed from the adjacent period.`,
    `Energy and self-knowledge language persisted across ${entries.length} entries.`,
  ];
  const stages = [
    'How you entered',
    'What you were seeking',
    'What challenged you',
    'What changed',
    'Who you were becoming',
    'What remained unresolved',
  ];

  return {
    id: `chapter-${index + 1}`,
    title,
    start: first.entry_date,
    end: status === 'current' || status === 'emerging' ? null : last.entry_date,
    status,
    themes,
    thesis: `Your entries in this period were most consistently shaped by ${joinThemeLabels(themes.map((theme) => theme.key))}.`,
    detectionReasons,
    corePursuit: `Making room for ${primaryLabel.toLowerCase()} while keeping ${secondaryLabel.toLowerCase()} in view.`,
    energySignature: previousChapter
      ? `${primaryLabel} became more prominent than in ${previousChapter.title}, while energy language shifted with the new theme mix.`
      : `Energy language appeared most often alongside ${primaryLabel.toLowerCase()} and ${secondaryLabel.toLowerCase()}.`,
    recurringDrain: `Reduced capacity appeared repeatedly when the demands around ${primaryLabel.toLowerCase()} and ${secondaryLabel.toLowerCase()} competed for attention.`,
    hiddenNeed: `This chapter may have been shaped by a need to make ${primaryLabel.toLowerCase()} feel compatible with ${secondaryLabel.toLowerCase()}.`,
    centralTension: { left: primaryLabel, right: secondaryLabel },
    goalTrajectory: [
      `${primaryLabel} became a more sustained focus.`,
      `${secondaryLabel} remained present but changed relative position.`,
      `${themeLabels[2] ?? 'A new concern'} began to influence the chapter's direction.`,
    ],
    emergingIdentity: `Your entries increasingly describe someone learning how to hold ${primaryLabel.toLowerCase()} and ${secondaryLabel.toLowerCase()} together.`,
    arc: stages.map((stage, stageIndex) => {
      const stageEvidence = evidence.slice(stageIndex, stageIndex + 3);
      return {
        stage,
        interpretation:
          stageIndex < 3
            ? `The earlier entries place more emphasis on understanding what ${primaryLabel.toLowerCase()} required.`
            : `Later entries use more deliberate language about how ${primaryLabel.toLowerCase()} could continue alongside ${secondaryLabel.toLowerCase()}.`,
        dateRange,
        evidenceCount: stageEvidence.length,
        evidence: stageEvidence,
        turningPoint:
          stageIndex === 3
            ? `Possible shift in how ${primaryLabel.toLowerCase()} was approached`
            : undefined,
      };
    }),
    echoes: previousChapter
      ? [
          {
            earlierChapter: previousChapter.title,
            repeated: `Both chapters gave sustained attention to ${secondaryLabel.toLowerCase()}.`,
            changed: `${primaryLabel} became more prominent in the selected chapter, changing how the repeated concern was described.`,
          },
        ]
      : [],
    carryForward: [
      {
        label: 'What this chapter gave you',
        text: `A clearer language for the relationship between ${primaryLabel.toLowerCase()} and ${secondaryLabel.toLowerCase()}.`,
      },
      {
        label: 'What remained unresolved',
        text: `How to protect both needs when they compete for the same capacity.`,
      },
      {
        label: 'What you left behind',
        text: `An earlier balance of attention that no longer matched the entries in this period.`,
      },
      {
        label: 'What entered the next chapter',
        text: `${primaryLabel} became part of the conditions shaping what followed.`,
      },
    ],
    unresolvedQuestion: `What would it mean to carry the strongest part of ${primaryLabel.toLowerCase()} forward without losing ${secondaryLabel.toLowerCase()}?`,
    evidence,
  };
}

function monthsBetween(first: string, last: string) {
  const start = new Date(`${first}T00:00:00Z`);
  const end = new Date(`${last}T00:00:00Z`);
  return Math.max(
    1,
    (end.getUTCFullYear() - start.getUTCFullYear()) * 12 +
      end.getUTCMonth() -
      start.getUTCMonth() +
      1,
  );
}

export function deriveJourneyViewModel(
  entries: JourneyEntry[],
  range: JourneyRange,
): JourneyViewModel {
  const sorted = [...entries].sort((left, right) =>
    left.entry_date.localeCompare(right.entry_date),
  );
  const segments = chapterSegments(sorted);
  const chapters = segments.reduce<JourneyChapter[]>(
    (result, segment, index) => {
      result.push(makeChapter(segment, index, segments.length, result.at(-1)));
      return result;
    },
    [],
  );
  const firstThemes = rankedThemes(
    sorted.slice(0, Math.max(1, Math.ceil(sorted.length / 3))),
  ).slice(0, 2);
  const lastThemes = rankedThemes(
    sorted.slice(-Math.max(1, Math.ceil(sorted.length / 3))),
  ).slice(0, 2);
  const from = sorted[0]?.entry_date ?? '';
  const to = sorted.at(-1)?.entry_date ?? '';

  return {
    entryCount: sorted.length,
    from,
    to,
    coverageLabel:
      sorted.length > 0
        ? `${sorted.length} entries across ${monthsBetween(from, to)} months`
        : 'No coverage in this period',
    summary:
      sorted.length > 0
        ? `Attention moved from ${joinThemeLabels(firstThemes)} toward ${joinThemeLabels(lastThemes)} across the selected period.`
        : '',
    streamData: buildStreamData(sorted, range),
    chapters,
    boundaries: chapters.slice(1).map((chapter, index) => {
      const previous = chapters[index]!;
      const boundaryEntries = [
        ...segments[index]!.slice(-2),
        ...segments[index + 1]!.slice(0, 2),
      ];
      return {
        id: `boundary-${index + 1}`,
        date: chapter.start,
        previousChapterId: previous.id,
        nextChapterId: chapter.id,
        reasons: chapter.detectionReasons,
        entryCount: boundaryEntries.length,
        evidence: evidenceFrom(
          boundaryEntries,
          `Boundary between ${previous.title} and ${chapter.title}`,
        ),
      };
    }),
  };
}
