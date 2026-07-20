import type {
  HiddenDriverData,
  InnerTensionData,
  RecurringLoopData,
  ReflectionTab,
} from './api-schema';

export type {
  HiddenDriverData,
  InnerTension,
  InnerTensionData,
  RecurringLoopData,
  RecurringLoopStep,
  ReflectionRange,
  ReflectionTab,
} from './api-schema';

export type ReflectionView =
  'hidden-drivers' | 'recurring-loops' | 'inner-tensions';
export type ReflectionResponse = 'resonates' | 'partly' | 'rejected';

export const reflectionTabByView: Record<
  ReflectionView,
  Exclude<ReflectionTab, 'all'>
> = {
  'hidden-drivers': 'hiddenDriver',
  'recurring-loops': 'recurringLoop',
  'inner-tensions': 'innerTension',
};

export interface JournalEntry {
  entry_date: string;
  content: {
    added_energy: string[];
    drained_energy: string[];
    self_knowledge: string[];
  };
}

export interface ReflectionViewModel {
  entryCount: number;
  from: string | null;
  to: string | null;
  hiddenDriver: HiddenDriverData;
  loop: RecurringLoopData;
  innerTension: InnerTensionData;
}
