import type { EvidenceItem } from '@/types/evidence';

export type ReflectionRange = '7d' | '30d' | 'all';

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
    drivers: string[];
    evidenceStrength: string[];
    evidence: EvidenceItem[];
  };
  loop: {
    steps: ReflectionLoopStep[];
    protection: string;
    interruption: string;
    evidence: EvidenceItem[];
  };
  tensions: InnerTension[];
  focus: {
    title: string;
    body: string;
    experiment: string;
    evidence: EvidenceItem[];
  };
}
