export type StatusTone =
  'neutral' | 'processing' | 'success' | 'warning' | 'error';

export const entryStatusPresentation = {
  completed: { label: 'Complete', filterLabel: 'Complete', tone: 'success' },
  processing: {
    label: 'Processing',
    filterLabel: 'Processing',
    tone: 'processing',
  },
  failed: {
    label: 'Processing failed',
    filterLabel: 'Failed',
    tone: 'error',
  },
} as const satisfies Record<
  string,
  { label: string; filterLabel: string; tone: StatusTone }
>;

export type EntryStatus = keyof typeof entryStatusPresentation;

export const approvalStatusPresentation = {
  pending_approval: { label: 'Needs review', tone: 'warning' },
  approved: { label: 'Approved', tone: 'success' },
  rejected: { label: 'Not saved', tone: 'neutral' },
} as const satisfies Record<string, { label: string; tone: StatusTone }>;

export type ApprovalStatus = keyof typeof approvalStatusPresentation;

export const extractedItemKindPresentation = {
  idea: { label: 'Idea', pluralLabel: 'Ideas' },
  memory: { label: 'Memory', pluralLabel: 'Memories' },
} as const;

export type ExtractedItemKind = keyof typeof extractedItemKindPresentation;

export const journeyChapterStatusPresentation = {
  completed: { label: 'completed', tone: 'neutral' },
  current: { label: 'current', tone: 'success' },
  emerging: { label: 'emerging', tone: 'neutral' },
} as const satisfies Record<string, { label: string; tone: StatusTone }>;

export type ChapterStatus = keyof typeof journeyChapterStatusPresentation;

export const savedItemStatusPresentation = {
  label: 'Saved',
  tone: 'success',
} as const satisfies { label: string; tone: StatusTone };
