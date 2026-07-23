'use client';

import { Eye, MessageSquareText } from 'lucide-react';
import { useState } from 'react';

import { AppButton } from '@/components/design-system';
import { FormField, TextArea } from '@/components/forms';
import { EvidenceDrawer, ReviewItemCard } from '@/components/shared';
import {
  reviewCorrectionMaxLength,
  reviewNoteMaxLength,
  type ReviewVerdict,
} from './api-schema';
import type { ReviewItem } from './model';
import { ReviewCategoryBadge } from './review-category-badge';
import type { SubmitReviewFeedbackInput } from './repository';

interface FeedbackAction {
  label: string;
  verdict: ReviewVerdict;
  variant: 'accentOutline' | 'outline' | 'rejectOutline';
}

const entryActions = [
  { label: 'Accurate', verdict: 'accurate', variant: 'accentOutline' },
  { label: 'Partly accurate', verdict: 'partly_accurate', variant: 'outline' },
  { label: 'Not accurate', verdict: 'not_accurate', variant: 'rejectOutline' },
] as const satisfies readonly FeedbackAction[];

const patternActions = [
  { label: 'Resonates', verdict: 'resonates', variant: 'accentOutline' },
  { label: 'Partly true', verdict: 'partly_true', variant: 'outline' },
  { label: 'Not true', verdict: 'not_true', variant: 'rejectOutline' },
] as const satisfies readonly FeedbackAction[];

export interface ReviewQueueItemProps {
  item: ReviewItem;
  disabled?: boolean;
  loadingVerdict?: ReviewVerdict;
  onFeedback: (input: SubmitReviewFeedbackInput) => void;
}

export function ReviewQueueItem({
  disabled = false,
  item,
  loadingVerdict,
  onFeedback,
}: ReviewQueueItemProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(
    Boolean(item.feedback?.correctedStatement || item.feedback?.note),
  );
  const [correctedStatement, setCorrectedStatement] = useState(
    item.feedback?.correctedStatement ?? '',
  );
  const [note, setNote] = useState(item.feedback?.note ?? '');
  const actions =
    item.scope === 'entry_insight' ? entryActions : patternActions;
  const evidence =
    item.scope === 'entry_insight'
      ? [
          {
            id: item.sourceEntryIds[0],
            date: item.sourceDates[0],
            source: 'Entry insight source',
            text:
              item.sourceQuote ??
              'This journal entry contributed validated evidence to this insight.',
          },
        ]
      : item.sourceDates.map((date) => ({
          id: `${item.id}:${date}`,
          date,
          source: 'Pattern evidence date',
          text: 'One or more journal entries on this date contributed validated evidence to this pattern.',
          interpretation: item.statement,
        }));
  const contextId = `review-context-${item.id}`;
  const sourceLabel =
    item.scope === 'entry_insight'
      ? 'View source'
      : evidence.length === 1
        ? 'View evidence date'
        : `View ${evidence.length} evidence dates`;

  return (
    <li>
      <article>
        <ReviewItemCard
          actions={
            <div className="space-y-4">
              <div className="flex flex-wrap gap-3">
                <AppButton
                  aria-label={`View source evidence for: ${item.statement}`}
                  disabled={disabled}
                  leftIcon={<Eye aria-hidden="true" />}
                  onClick={() => setDrawerOpen(true)}
                  variant="link"
                >
                  {sourceLabel}
                </AppButton>
                <AppButton
                  aria-controls={contextId}
                  aria-expanded={contextOpen}
                  disabled={disabled}
                  leftIcon={<MessageSquareText aria-hidden="true" />}
                  onClick={() => setContextOpen((current) => !current)}
                  variant="ghost"
                >
                  {contextOpen ? 'Hide context' : 'Add correction or note'}
                </AppButton>
              </div>

              {contextOpen ? (
                <div className="grid gap-4 sm:grid-cols-2" id={contextId}>
                  <FormField
                    description="Optional. Replace Orion's wording with language that feels more accurate."
                    id={`review-correction-${item.id}`}
                    label="Corrected statement"
                  >
                    <TextArea
                      disabled={disabled}
                      maxLength={reviewCorrectionMaxLength}
                      onChange={(event) =>
                        setCorrectedStatement(event.target.value)
                      }
                      value={correctedStatement}
                    />
                  </FormField>
                  <FormField
                    description="Optional context for this feedback."
                    id={`review-note-${item.id}`}
                    label="Note"
                  >
                    <TextArea
                      disabled={disabled}
                      maxLength={reviewNoteMaxLength}
                      onChange={(event) => setNote(event.target.value)}
                      value={note}
                    />
                  </FormField>
                </div>
              ) : null}

              <div
                aria-label={`Feedback for: ${item.statement}`}
                className="flex flex-wrap gap-3"
                role="group"
              >
                {actions.map((action) => (
                  <AppButton
                    aria-label={`${action.label}: ${item.statement}`}
                    disabled={disabled || loadingVerdict !== undefined}
                    key={action.verdict}
                    loading={loadingVerdict === action.verdict}
                    loadingLabel={`Saving ${action.label} feedback for: ${item.statement}`}
                    onClick={() =>
                      onFeedback({
                        itemId: item.id,
                        scope: item.scope,
                        feedback: {
                          verdict: action.verdict,
                          correctedStatement,
                          note,
                        },
                      })
                    }
                    shape="pill"
                    variant={action.variant}
                  >
                    {action.label}
                  </AppButton>
                ))}
              </div>
            </div>
          }
          content={item.statement}
          status={<ReviewCategoryBadge category={item.category} />}
        />
      </article>

      <EvidenceDrawer
        contentIsQuote={
          item.scope === 'entry_insight' && Boolean(item.sourceQuote)
        }
        contentLabel={
          item.scope === 'entry_insight' && item.sourceQuote
            ? undefined
            : 'Evidence context'
        }
        description={
          item.scope === 'entry_insight' && item.sourceQuote
            ? "The exact journal wording is shown separately from Orion's interpretation."
            : item.scope === 'entry_insight'
              ? 'This date identifies the journal entry that contributed validated evidence. Full journal text remains in Entries.'
              : `${item.sourceEntryIds.length} ${
                  item.sourceEntryIds.length === 1
                    ? 'journal entry'
                    : 'journal entries'
                } across ${item.sourceDates.length} ${
                  item.sourceDates.length === 1 ? 'date' : 'dates'
                } contributed validated evidence. Full journal text remains in Entries.`
        }
        items={evidence}
        onOpenChange={setDrawerOpen}
        open={drawerOpen}
      />
    </li>
  );
}
