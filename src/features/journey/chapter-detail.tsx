'use client';

import {
  ArrowDown,
  ArrowRight,
  Check,
  Minus,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import { useState, type FormEvent } from 'react';

import { Surface } from '@/components/cards';
import { StatusBadge, ThemeBadge } from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import { TextInput } from '@/components/forms';
import { Tabs } from '@/components/navigation';
import { formatLongDate } from '@/lib/date';
import type { EvidenceItem } from '@/types/evidence';

import type { JourneyChapter } from './model';

export interface ChapterDetailProps {
  chapter: JourneyChapter;
  onRenameChapter: (title: string) => void;
  onViewEvidence: (items?: EvidenceItem[]) => void;
}

type ChapterPanelProps = Pick<ChapterDetailProps, 'chapter' | 'onViewEvidence'>;

function Interpretation({
  children,
  label,
  onViewEvidence,
}: {
  children: string;
  label: string;
  onViewEvidence: (items?: EvidenceItem[]) => void;
}) {
  return (
    <div className="border-border space-y-3 border-t pt-6 first:border-t-0 first:pt-0">
      <Typography variant="eyebrow">{label}</Typography>
      <Typography variant="body">{children}</Typography>
      <AppButton onClick={() => onViewEvidence()} size="compact" variant="link">
        Why am I seeing this?
      </AppButton>
    </div>
  );
}

function ChapterDna({ chapter, onViewEvidence }: ChapterPanelProps) {
  const directionIcon = {
    fading: TrendingDown,
    rising: TrendingUp,
    stable: Minus,
  };
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Surface className="gap-6 p-6">
        <Typography as="h3" variant="componentTitle">
          Dominant themes
        </Typography>
        <div className="space-y-4">
          {chapter.themes.map((theme) => {
            const DirectionIcon = directionIcon[theme.direction];
            return (
              <div
                className="flex items-center justify-between gap-4"
                key={theme.key}
              >
                <ThemeBadge theme={theme.key} />
                <span className="type-metadata text-muted-foreground inline-flex items-center gap-2">
                  <DirectionIcon aria-hidden="true" className="size-4" />
                  {theme.direction}
                </span>
              </div>
            );
          })}
        </div>
        <Interpretation label="Core pursuit" onViewEvidence={onViewEvidence}>
          {chapter.corePursuit}
        </Interpretation>
        <Interpretation
          label="Energy signature"
          onViewEvidence={onViewEvidence}
        >
          {chapter.energySignature}
        </Interpretation>
        <Interpretation label="Recurring drain" onViewEvidence={onViewEvidence}>
          {chapter.recurringDrain}
        </Interpretation>
      </Surface>

      <Surface className="gap-6 p-6">
        <Interpretation
          label="Possible hidden need"
          onViewEvidence={onViewEvidence}
        >
          {chapter.hiddenNeed}
        </Interpretation>
        <div className="space-y-3">
          <Typography variant="eyebrow">Central tension</Typography>
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge
              label={chapter.centralTension.left}
              variant="neutral"
            />
            <Typography aria-hidden="true" variant="metadata">
              and
            </Typography>
            <StatusBadge
              label={chapter.centralTension.right}
              variant="neutral"
            />
          </div>
          <div
            aria-label="Both needs are valid"
            className="flex items-center gap-3"
          >
            <span aria-hidden="true" className="bg-accent radius-pill size-3" />
            <span aria-hidden="true" className="bg-border h-px flex-1" />
            <span
              aria-hidden="true"
              className="bg-primary radius-pill size-3"
            />
          </div>
          <AppButton
            onClick={() => onViewEvidence()}
            size="compact"
            variant="link"
          >
            Why am I seeing this?
          </AppButton>
        </div>
        <div className="space-y-3">
          <Typography variant="eyebrow">Goal trajectory</Typography>
          <ul className="type-body space-y-2">
            {chapter.goalTrajectory.map((goal) => (
              <li className="flex gap-3" key={goal}>
                <Check
                  aria-hidden="true"
                  className="text-accent mt-1 size-4 shrink-0"
                />
                {goal}
              </li>
            ))}
          </ul>
          <AppButton
            onClick={() => onViewEvidence()}
            size="compact"
            variant="link"
          >
            Why am I seeing this?
          </AppButton>
        </div>
        <Interpretation
          label="Emerging identity"
          onViewEvidence={onViewEvidence}
        >
          {chapter.emergingIdentity}
        </Interpretation>
      </Surface>
    </div>
  );
}

function TransformationArc({ chapter, onViewEvidence }: ChapterPanelProps) {
  const [turningPointResponse, setTurningPointResponse] = useState<string>();
  return (
    <Surface className="gap-6 p-6">
      <div className="space-y-2">
        <Typography as="h3" variant="componentTitle">
          Transformation arc
        </Typography>
        <Typography className="text-muted-foreground" variant="bodySmall">
          A tentative sequence inferred from the language in this chapter.
        </Typography>
      </div>
      <ol className="grid gap-4 lg:grid-cols-6">
        {chapter.arc.map((stage, index) => (
          <li className="relative flex gap-4 lg:block" key={stage.stage}>
            <div className="flex flex-col items-center lg:flex-row">
              <span className="bg-primary text-primary-foreground type-metadata radius-pill grid size-8 shrink-0 place-items-center">
                {index + 1}
              </span>
              {index < chapter.arc.length - 1 ? (
                <>
                  <ArrowDown
                    aria-hidden="true"
                    className="text-muted-foreground my-2 size-4 lg:hidden"
                  />
                  <ArrowRight
                    aria-hidden="true"
                    className="text-muted-foreground mx-2 hidden size-4 lg:block"
                  />
                </>
              ) : null}
            </div>
            <div className="space-y-2 lg:mt-4">
              <Typography as="h4" variant="metadata">
                {stage.stage}
              </Typography>
              <Typography className="text-muted-foreground" variant="bodySmall">
                {stage.interpretation}
              </Typography>
              <div className="space-y-1">
                <Typography className="text-muted-foreground" variant="eyebrow">
                  {stage.dateRange}
                </Typography>
                <Typography className="text-muted-foreground" variant="eyebrow">
                  {stage.evidenceCount} supporting entries
                </Typography>
              </div>
              {stage.turningPoint ? (
                <StatusBadge label={stage.turningPoint} variant="neutral" />
              ) : null}
              <details>
                <summary className="type-button radius-control min-touch-target focus-visible:ring-ring cursor-pointer focus-visible:ring-2 focus-visible:outline-none">
                  Review exact excerpts
                </summary>
                <AppButton
                  disabled={stage.evidence.length === 0}
                  onClick={() => onViewEvidence(stage.evidence)}
                  size="compact"
                  variant="link"
                >
                  Open supporting entries
                </AppButton>
              </details>
              {stage.turningPoint ? (
                <div
                  aria-label="Possible turning point feedback"
                  className="flex flex-wrap gap-2"
                  role="group"
                >
                  {[
                    ['confirmed', 'This happened'],
                    ['rename', 'Rename this transition'],
                    ['rejected', 'This is not what happened'],
                  ].map(([value, label]) => (
                    <AppButton
                      aria-pressed={turningPointResponse === value}
                      key={value}
                      onClick={() => setTurningPointResponse(value)}
                      size="compact"
                      variant={
                        turningPointResponse === value ? 'secondary' : 'ghost'
                      }
                    >
                      {label}
                    </AppButton>
                  ))}
                </div>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
      <AppButton onClick={() => onViewEvidence()} size="compact" variant="link">
        View the entries behind this arc
      </AppButton>
      <div className="border-border space-y-3 border-t pt-6">
        <Typography variant="eyebrow">What may remain unresolved</Typography>
        <Typography as="blockquote" variant="reflectionCardStatement">
          {chapter.unresolvedQuestion}
        </Typography>
      </div>
      <Typography
        aria-live="polite"
        className="text-muted-foreground"
        variant="bodySmall"
      >
        {turningPointResponse
          ? `Turning-point response saved: ${turningPointResponse}.`
          : 'Possible transitions remain tentative until you confirm them.'}
      </Typography>
    </Surface>
  );
}

function PatternEchoes({ chapter, onViewEvidence }: ChapterPanelProps) {
  if (chapter.echoes.length === 0) {
    return (
      <Surface className="items-start gap-4 p-6">
        <Typography as="h3" variant="componentTitle">
          Pattern Echoes need more history
        </Typography>
        <Typography
          className="text-muted-foreground text-measure"
          variant="body"
        >
          Orion will compare this chapter with earlier phases once enough
          history develops.
        </Typography>
      </Surface>
    );
  }
  return (
    <div className="space-y-6">
      {chapter.echoes.map((echo) => (
        <Surface className="gap-6 p-6" key={echo.earlierChapter}>
          <div className="space-y-2">
            <Typography variant="eyebrow">Echo of</Typography>
            <Typography as="h3" variant="componentTitle">
              {echo.earlierChapter}
            </Typography>
          </div>
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-2">
              <Typography variant="metadata">What appears repeated</Typography>
              <Typography className="text-muted-foreground" variant="body">
                {echo.repeated}
              </Typography>
            </div>
            <div className="space-y-2">
              <Typography variant="metadata">
                What appears different this time
              </Typography>
              <Typography className="text-muted-foreground" variant="body">
                {echo.changed}
              </Typography>
            </div>
          </div>
          <AppButton
            onClick={() => onViewEvidence()}
            size="compact"
            variant="link"
          >
            Compare supporting entries
          </AppButton>
        </Surface>
      ))}
    </div>
  );
}

function CarryForward({ chapter, onViewEvidence }: ChapterPanelProps) {
  const [response, setResponse] = useState<string>();
  return (
    <Surface className="gap-6 p-6">
      <div className="grid gap-4 md:grid-cols-2">
        {chapter.carryForward.map((item) => (
          <div
            className="bg-muted radius-control space-y-2 p-4"
            key={item.label}
          >
            <Typography variant="eyebrow">{item.label}</Typography>
            <Typography variant="bodySmall">{item.text}</Typography>
          </div>
        ))}
      </div>
      <div className="border-border space-y-3 border-t pt-6">
        <Typography variant="eyebrow">A question to carry forward</Typography>
        <Typography as="blockquote" variant="reflectionCardStatement">
          {chapter.unresolvedQuestion}
        </Typography>
      </div>
      <div
        className="flex flex-wrap gap-3"
        role="group"
        aria-label="Carry-forward response"
      >
        {['Keep this', 'Edit focus', 'Not for me'].map((label) => (
          <AppButton
            aria-pressed={response === label}
            key={label}
            onClick={() => setResponse(label)}
            size="compact"
            variant={response === label ? 'primary' : 'secondary'}
          >
            {label}
          </AppButton>
        ))}
      </div>
      <AppButton onClick={() => onViewEvidence()} size="compact" variant="link">
        Why am I seeing this?
      </AppButton>
      <Typography
        aria-live="polite"
        className="text-muted-foreground"
        variant="metadata"
      >
        {response
          ? `Response saved: ${response}.`
          : 'Your response helps Orion learn without changing your original journal.'}
      </Typography>
    </Surface>
  );
}

export function ChapterDetail({
  chapter,
  onRenameChapter,
  onViewEvidence,
}: ChapterDetailProps) {
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [draftTitle, setDraftTitle] = useState(chapter.title);
  const [showDetectionReasons, setShowDetectionReasons] = useState(false);

  function submitTitle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextTitle = draftTitle.trim();
    if (!nextTitle) return;
    onRenameChapter(nextTitle);
    setIsEditingTitle(false);
  }

  return (
    <section aria-labelledby="selected-chapter-heading" className="space-y-6">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge
            label={chapter.status}
            variant={chapter.status === 'current' ? 'success' : 'neutral'}
          />
          <Typography className="text-muted-foreground" variant="metadata">
            {formatLongDate(chapter.start)}–
            {chapter.end ? formatLongDate(chapter.end) : 'Present'}
          </Typography>
          {chapter.themes.map((theme) => (
            <ThemeBadge key={theme.key} theme={theme.key} />
          ))}
        </div>
        {isEditingTitle ? (
          <form
            className="flex flex-col gap-3 sm:flex-row"
            onSubmit={submitTitle}
          >
            <TextInput
              aria-label="Chapter name"
              onChange={(event) => setDraftTitle(event.target.value)}
              value={draftTitle}
            />
            <div className="flex gap-2">
              <AppButton size="compact" type="submit">
                Save name
              </AppButton>
              <AppButton
                onClick={() => {
                  setDraftTitle(chapter.title);
                  setIsEditingTitle(false);
                }}
                size="compact"
                type="button"
                variant="ghost"
              >
                Cancel
              </AppButton>
            </div>
          </form>
        ) : (
          <Typography
            as="h2"
            id="selected-chapter-heading"
            variant="reflectionCardStatement"
          >
            {chapter.title}
          </Typography>
        )}
        <Typography
          className="text-measure text-muted-foreground"
          variant="journalExcerpt"
        >
          {chapter.thesis}
        </Typography>
        <div className="flex flex-wrap gap-2">
          <AppButton
            onClick={() => setIsEditingTitle(true)}
            size="compact"
            variant="ghost"
          >
            Edit chapter name
          </AppButton>
          <AppButton
            aria-expanded={showDetectionReasons}
            onClick={() => setShowDetectionReasons((current) => !current)}
            size="compact"
            variant="ghost"
          >
            Why was this detected?
          </AppButton>
          <AppButton
            onClick={() => onViewEvidence()}
            size="compact"
            variant="link"
          >
            View evidence
          </AppButton>
        </div>
      </div>
      {showDetectionReasons ? (
        <Surface className="bg-muted gap-4 p-4" role="status">
          <Typography as="h3" variant="componentTitle">
            Why Orion proposed this chapter
          </Typography>
          <ul className="type-body-small list-disc space-y-2 pl-6">
            {chapter.detectionReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <Typography className="text-muted-foreground" variant="bodySmall">
            This is a tentative interpretation. You can rename it or reject
            evidence that does not match your experience.
          </Typography>
        </Surface>
      ) : null}
      <Tabs
        ariaLabel="Chapter analysis"
        items={[
          {
            value: 'dna',
            label: 'Chapter DNA',
            content: (
              <ChapterDna chapter={chapter} onViewEvidence={onViewEvidence} />
            ),
          },
          {
            value: 'arc',
            label: 'Transformation Arc',
            content: (
              <TransformationArc
                chapter={chapter}
                onViewEvidence={onViewEvidence}
              />
            ),
          },
          {
            value: 'echoes',
            label: 'Pattern Echoes',
            content: (
              <PatternEchoes
                chapter={chapter}
                onViewEvidence={onViewEvidence}
              />
            ),
          },
          {
            value: 'carry',
            label: 'Carry Forward',
            content: (
              <CarryForward chapter={chapter} onViewEvidence={onViewEvidence} />
            ),
          },
        ]}
      />
    </section>
  );
}
