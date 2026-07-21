/** Test-only adapter for legacy mock-store evidence. */
import type { EvidenceItem } from './api-schema';

interface ApprovedReflectionEvidence {
  content: string;
  entryDate: string;
}

export function approvedEvidenceToReflectionEvidence(
  items: ApprovedReflectionEvidence[],
): EvidenceItem[] {
  return items.map((item, index) => ({
    id: `40000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
    entryDate: item.entryDate,
    sourceLabel: 'Self-knowledge',
    quote: item.content,
    interpretation:
      'This approved reflection contributes to the test-only aggregate view.',
    theme: null,
    supports: 'Approved reflective evidence',
  }));
}
