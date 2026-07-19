import type { ThemeKey } from '@/config/design-system';

export interface EvidenceItem {
  id: string;
  date: string;
  source: string;
  text: string;
  interpretation?: string;
  theme?: ThemeKey;
  rank?: 'primary' | 'secondary' | 'tertiary';
  supports?: string;
}
