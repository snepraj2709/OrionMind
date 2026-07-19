import type { ThemeKey } from '@/config/design-system';
import type {
  ApprovalStatus,
  EntryStatus,
  ExtractedItemKind,
} from '@/config/status';

export interface ExtractedItem {
  id: string;
  content: string;
  kind: ExtractedItemKind;
  status: ApprovalStatus;
}

export interface EntrySummary {
  id: string;
  content: string;
  date: string;
  status: EntryStatus;
  inputType: 'text' | 'voice';
  themes: ThemeKey[];
}

export interface EntryDetail extends EntrySummary {
  ideas: ExtractedItem[];
  memories: ExtractedItem[];
  processingError?: string;
}

export interface ApprovalRecord extends ExtractedItem {
  entryId: string;
  entryDate: string;
}

export interface SavedItemRecord {
  id: string;
  content: string;
  entryId: string;
  entryDate: string;
  kind: ExtractedItemKind;
}
