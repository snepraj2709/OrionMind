import type { ThemeKey } from '@/config/design-system';
import type { ChapterStatus } from '@/config/status';
import type { EvidenceItem } from '@/types/evidence';

export type { ChapterStatus } from '@/config/status';
export type JourneyRange = '6m' | '1y' | '2y' | '3y' | '5y' | 'all';
export type ThemeRank = 'primary' | 'secondary' | 'tertiary';
export type ThemeValue =
  | 'career'
  | 'money'
  | 'health'
  | 'love_life'
  | 'family_friends'
  | 'personal_growth'
  | 'fun_recreation'
  | 'home_lifestyle';

export interface EntryTheme {
  rank: ThemeRank;
  value: ThemeValue;
}

export interface JourneyEntry {
  entry_date: string;
  theme: EntryTheme[];
  content: {
    added_energy: string[];
    drained_energy: string[];
    self_knowledge: string[];
  };
}

export interface JourneyEntriesResult {
  entries: JourneyEntry[];
  totalAvailable: number;
}

export interface JourneySteamPoint {
  date: string;
  label: string;
  values: Record<ThemeKey, number>;
}

export interface JourneyResponse extends JourneyEntriesResult {
  range: JourneyRange;
  stream: JourneySteamPoint[];
}

export interface JourneyStatusResponse {
  enabled: boolean;
  daysSinceSignup: number;
  entriesAdded: number;
}

export interface ThemeRiverPoint {
  bucket: string;
  entryCount: number;
  values: Record<ThemeKey, number>;
  representativeSentence: string;
  rising: ThemeKey[];
  fading: ThemeKey[];
}

export interface JourneyChapter {
  id: string;
  title: string;
  start: string;
  end: string | null;
  status: ChapterStatus;
  themes: Array<{
    key: ThemeKey;
    rank: ThemeRank;
    direction: 'rising' | 'stable' | 'fading';
  }>;
  thesis: string;
  detectionReasons: string[];
  corePursuit: string;
  energySignature: string;
  recurringDrain: string;
  hiddenNeed: string;
  centralTension: { left: string; right: string };
  goalTrajectory: string[];
  emergingIdentity: string;
  arc: Array<{
    stage: string;
    interpretation: string;
    dateRange: string;
    evidenceCount: number;
    evidence: EvidenceItem[];
    turningPoint?: string;
  }>;
  echoes: Array<{ earlierChapter: string; repeated: string; changed: string }>;
  carryForward: Array<{ label: string; text: string }>;
  unresolvedQuestion: string;
  evidence: EvidenceItem[];
}

export interface JourneyBoundary {
  id: string;
  date: string;
  previousChapterId: string;
  nextChapterId: string;
  reasons: string[];
  entryCount: number;
  evidence: EvidenceItem[];
}

export interface JourneyViewModel {
  entryCount: number;
  from: string;
  to: string;
  coverageLabel: string;
  summary: string;
  streamData: ThemeRiverPoint[];
  chapters: JourneyChapter[];
  boundaries: JourneyBoundary[];
}
