import type { EvidenceItem } from '@/types/evidence';

export type ReflectionRange = '7d' | '30d' | 'all';
export type ReflectionView =
  'hidden-drivers' | 'recurring-loops' | 'inner-tensions';
export type ReflectionResponse = 'resonates' | 'partly' | 'rejected';

export interface JournalEntry {
  entry_date: string;
  content: {
    added_energy: string[];
    drained_energy: string[];
    self_knowledge: string[];
  };
}

export interface ReflectionEntriesResult {
  entries: JournalEntry[];
  totalAvailable: number;
}

export interface ReflectionLoopStep {
  id: string;
  text: string;
  entryCount: number;
  evidence: EvidenceItem[];
}

export interface InnerTension {
  id: string;
  leftTitle: string;
  leftBody: string;
  rightTitle: string;
  rightBody: string;
  integration: string;
  dates: string[];
  evidence: EvidenceItem[];
}

export interface ReflectionViewModel {
  entryCount: number;
  from: string;
  to: string;
  hiddenDriver: {
    statement: string;
    underlyingNeed: string;
    drivers: readonly string[];
    evidenceStrength: readonly string[];
    evidence: EvidenceItem[];
  };
  loop: {
    title: string;
    description: string;
    steps: ReflectionLoopStep[];
    protection: string;
    interruption: string;
    evidence: EvidenceItem[];
  };
  tensions: InnerTension[];
}
