import { Brain, Check, Lightbulb, Mic, Sparkles, X } from 'lucide-react';

import { Typography } from '@/components/design-system';
import { themeRegistry, type ThemeKey } from '@/config/design-system';
import { JourneySteamgraph, type JourneySteamPoint } from '@/features/journey';

import styles from './landing.module.css';

const networkNodes = [
  { x: 54, y: 130, size: 6, tone: 'var(--primary)' },
  { x: 126, y: 82, size: 4, tone: 'var(--accent)' },
  { x: 208, y: 104, size: 5, tone: 'var(--theme-money)' },
  { x: 280, y: 52, size: 4, tone: 'var(--counterpoint)' },
  { x: 350, y: 122, size: 7, tone: 'var(--primary)' },
  { x: 430, y: 76, size: 4, tone: 'var(--theme-career)' },
  { x: 504, y: 142, size: 5, tone: 'var(--accent)' },
  { x: 148, y: 184, size: 5, tone: 'var(--theme-family-friends)' },
  { x: 252, y: 202, size: 4, tone: 'var(--theme-personal-growth)' },
  { x: 390, y: 196, size: 5, tone: 'var(--theme-love-life)' },
] as const;

export function LandingThoughtNetwork() {
  return (
    <svg
      aria-hidden="true"
      className="h-auto w-full"
      focusable="false"
      viewBox="0 0 560 260"
    >
      <g fill="none" stroke="var(--border)" strokeWidth="1.2">
        <path
          className={styles.networkPath}
          d="M54 130 C90 94 94 92 126 82 S180 92 208 104 S246 78 280 52"
        />
        <path
          className={styles.networkPath}
          d="M280 52 C318 70 324 112 350 122 S404 102 430 76 S474 116 504 142"
          style={{ animationDelay: '240ms' }}
        />
        <path
          className={styles.networkPath}
          d="M54 130 C92 150 112 176 148 184 S218 190 252 202 S348 210 390 196 S470 170 504 142"
          style={{ animationDelay: '480ms' }}
        />
        <path
          className={styles.networkPath}
          d="M126 82 C142 132 138 154 148 184 M208 104 C226 132 236 170 252 202 M350 122 C362 150 372 178 390 196"
          style={{ animationDelay: '720ms' }}
        />
      </g>
      {networkNodes.map((node, index) => (
        <g
          className={styles.networkNode}
          key={`${node.x}-${node.y}`}
          style={{ animationDelay: `${index * 180}ms` }}
        >
          <circle
            cx={node.x}
            cy={node.y}
            fill="var(--card)"
            r={node.size + 5}
            stroke="var(--border)"
          />
          <circle cx={node.x} cy={node.y} fill={node.tone} r={node.size} />
        </g>
      ))}
    </svg>
  );
}

export function LandingCapturePreview() {
  return (
    <div className="radius-card border-border bg-card space-y-4 border p-6">
      <div className="border-border flex items-center justify-between gap-4 border-b pb-4">
        <Typography variant="metadata">New entry</Typography>
        <Typography className="text-muted-foreground" variant="bodySmall">
          Today, 8:42 PM
        </Typography>
      </div>
      <div className="bg-input-background radius-interactive textarea-height p-4">
        <Typography className="text-muted-foreground" variant="body">
          I keep postponing the conversation even though I think about it every
          day. Part of me wants clarity, but another part is worried about what
          might change.
        </Typography>
      </div>
      <div className="flex items-center justify-between gap-4">
        <span className="text-muted-foreground flex items-center gap-2">
          <Mic aria-hidden="true" className="size-5" />
          <Typography as="span" variant="bodySmall">
            Voice or text
          </Typography>
        </span>
        <span className="bg-primary radius-interactive text-primary-foreground type-button px-4 py-3">
          Save entry
        </span>
      </div>
    </div>
  );
}

const reviewSuggestions = [
  {
    label: 'Idea',
    text: 'Have the conversation before uncertainty grows.',
  },
  {
    label: 'Memory',
    text: 'Previous difficult conversations brought relief afterward.',
  },
  {
    label: 'Reflection',
    text: 'Avoiding change may be creating a different kind of pressure.',
  },
] as const;

export function LandingReviewPreview() {
  return (
    <div className="radius-card border-border bg-card border p-6">
      <div className="border-border flex items-center justify-between gap-4 border-b pb-4">
        <Typography variant="metadata">Review suggestions</Typography>
        <Typography className="text-muted-foreground" variant="bodySmall">
          3 items
        </Typography>
      </div>
      <div className="divide-border divide-y">
        {reviewSuggestions.map((suggestion) => (
          <div className="space-y-3 py-4" key={suggestion.label}>
            <Typography className="text-primary" variant="eyebrow">
              {suggestion.label}
            </Typography>
            <Typography variant="bodySmall">{suggestion.text}</Typography>
            <div className="flex items-center gap-2">
              <span className="text-accent flex items-center gap-1">
                <Check aria-hidden="true" className="size-4" />
                <Typography as="span" variant="metadata">
                  Approve
                </Typography>
              </span>
              <span className="text-muted-foreground flex items-center gap-1">
                <X aria-hidden="true" className="size-4" />
                <Typography as="span" variant="metadata">
                  Reject
                </Typography>
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const insightCards = [
  {
    title: 'Ideas',
    text: 'Conversations worth beginning sooner.',
    icon: Lightbulb,
  },
  {
    title: 'Memories',
    text: 'Moments when honesty created relief.',
    icon: Brain,
  },
  {
    title: 'Reflections',
    text: 'Avoidance tends to increase the pressure you are trying to escape.',
    icon: Sparkles,
  },
] as const;

export function LandingInsightsPreview() {
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {insightCards.map((card) => {
        const Icon = card.icon;
        return (
          <article
            className="radius-card border-border bg-card space-y-4 border p-6"
            key={card.title}
          >
            <Icon aria-hidden="true" className="text-primary size-6" />
            <Typography as="h3" variant="componentTitle">
              {card.title}
            </Typography>
            <Typography className="text-muted-foreground" variant="bodySmall">
              {card.text}
            </Typography>
          </article>
        );
      })}
    </div>
  );
}

export function LandingHiddenDriverPreview() {
  return (
    <div className="radius-card border-border bg-card border p-6">
      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-4">
          <Typography as="blockquote" variant="reflectiveStatement">
            “I need to feel secure before I allow myself to move.”
          </Typography>
          <Typography className="text-muted-foreground" variant="body">
            Across several entries, uncertainty is linked with delaying action
            until every consequence feels controlled.
          </Typography>
          <div className="flex flex-wrap gap-2">
            {['Security', 'Control', 'Belonging'].map((driver) => (
              <span
                className="radius-pill border-border bg-background type-metadata border px-3 py-2"
                key={driver}
              >
                {driver}
              </span>
            ))}
          </div>
        </div>
        <div className="border-border space-y-4 border-t pt-6 md:border-t-0 md:border-l md:pt-0 md:pl-6">
          <Typography variant="eyebrow">
            Evidence from your reflections
          </Typography>
          <ul className="type-body-small text-muted-foreground space-y-3">
            <li>
              Career decisions are delayed until certainty feels complete.
            </li>
            <li>Relationship conflict is postponed to protect stability.</li>
            <li>
              New possibilities feel safer after someone else validates them.
            </li>
          </ul>
          <Typography className="text-primary" variant="metadata">
            Observed across 12 entries
          </Typography>
        </div>
      </div>
    </div>
  );
}

const loopStages = [
  'Overwhelm',
  'Postpone',
  'Temporary relief',
  'Issue escalates',
  'Guilt and anxiety',
  'Reduced capacity',
  'Avoidance repeats',
] as const;

const outerLoopStages = loopStages.slice(0, 6);

export function LandingRecurringLoopOrbital() {
  const centerX = 280;
  const centerY = 200;
  const radius = 148;

  return (
    <figure className="radius-card border-border bg-card overflow-x-auto border p-4">
      <svg
        aria-labelledby="recurring-loop-title recurring-loop-description"
        className="h-auto w-full min-w-[560px]"
        role="img"
        viewBox="0 0 560 460"
      >
        <title id="recurring-loop-title">A recurring avoidance loop</title>
        <desc id="recurring-loop-description">
          Overwhelm leads to postponing, temporary relief, an escalating issue,
          guilt and anxiety, reduced capacity, and repeating avoidance.
        </desc>
        <defs>
          <marker
            id="landing-loop-arrow"
            markerHeight="7"
            markerWidth="7"
            orient="auto"
            refX="6"
            refY="3.5"
          >
            <path d="M0 0 L7 3.5 L0 7 Z" fill="var(--primary)" />
          </marker>
        </defs>
        <circle
          cx={centerX}
          cy={centerY}
          fill="none"
          r={radius}
          stroke="var(--border)"
          strokeDasharray="5 7"
          strokeWidth="1.5"
        />
        <path
          d="M280 52 A148 148 0 1 1 267 52"
          fill="none"
          markerEnd="url(#landing-loop-arrow)"
          stroke="var(--primary)"
          strokeWidth="1.5"
        />
        {outerLoopStages.map((stage, index) => {
          const angle = (-90 + index * 60) * (Math.PI / 180);
          const x = centerX + Math.cos(angle) * radius;
          const y = centerY + Math.sin(angle) * radius;
          return (
            <g
              className={styles.loopStage}
              data-loop-stage
              key={stage}
              style={{ animationDelay: `${index * 1}s` }}
            >
              <circle
                cx={x}
                cy={y}
                fill="var(--card)"
                r="29"
                stroke="var(--border)"
              />
              <circle cx={x} cy={y} fill="var(--primary)" r="18" />
              <text
                dominantBaseline="middle"
                fill="var(--primary-foreground)"
                textAnchor="middle"
                x={x}
                y={y}
              >
                {index + 1}
              </text>
              <text
                className="type-body-small"
                fill="var(--foreground)"
                textAnchor="middle"
                x={x}
                y={y + (index === 0 ? -42 : 48)}
              >
                {stage}
              </text>
            </g>
          );
        })}
        <g
          className={styles.loopStage}
          data-loop-stage
          style={{ animationDelay: '6s' }}
        >
          <circle
            cx={centerX}
            cy={centerY}
            fill="var(--secondary)"
            r="62"
            stroke="var(--border)"
          />
          <circle
            cx={centerX}
            cy={centerY}
            fill="var(--card)"
            r="45"
            stroke="var(--primary)"
          />
          <text
            className="type-body-small"
            fill="var(--foreground)"
            textAnchor="middle"
            x={centerX}
            y={centerY - 4}
          >
            Avoidance
          </text>
          <text
            className="type-body-small"
            fill="var(--foreground)"
            textAnchor="middle"
            x={centerX}
            y={centerY + 16}
          >
            repeats
          </text>
        </g>
        <text
          className="type-body-small"
          fill="var(--muted-foreground)"
          textAnchor="middle"
          x={centerX}
          y="438"
        >
          The cycle reinforces itself
        </text>
      </svg>
    </figure>
  );
}

export function LandingInnerTensionPreview() {
  return (
    <div className="radius-card border-border bg-card space-y-6 border p-6">
      <div className="grid items-center gap-6 md:grid-cols-[1fr_auto_1fr]">
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="bg-primary radius-pill size-3"
            />
            <Typography
              as="h3"
              className="text-primary"
              variant="componentTitle"
            >
              Belonging
            </Typography>
          </div>
          <Typography variant="body">
            “I want to be accepted and supported by the people around me.”
          </Typography>
        </div>
        <div
          aria-label="Two needs held in tension"
          className="flex items-center justify-center"
        >
          <span className="bg-primary h-px w-10" />
          <span className="bg-card border-selection-strong radius-pill size-4 border" />
          <span className="bg-counterpoint h-px w-10" />
        </div>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="bg-counterpoint radius-pill size-3"
            />
            <Typography
              as="h3"
              className="text-counterpoint"
              variant="componentTitle"
            >
              Authenticity
            </Typography>
          </div>
          <Typography variant="body">
            “I want to live and speak according to what feels true to me.”
          </Typography>
        </div>
      </div>
      <div className="border-border space-y-3 border-t pt-6">
        <Typography variant="eyebrow">Possible integration</Typography>
        <Typography className="text-muted-foreground" variant="bodySmall">
          Find a possible integration rather than forcing one side to win.
        </Typography>
        <Typography as="blockquote" variant="journalExcerpt">
          “Clarity does not always come from choosing one side. Sometimes it
          comes from seeing both.”
        </Typography>
      </div>
    </div>
  );
}

const journeyPoints: JourneySteamPoint[] = [
  {
    date: '2023-09-01',
    label: 'Sep 2023',
    values: {
      career: 24,
      money: 15,
      health: 19,
      loveLife: 12,
      familyAndFriends: 20,
      personalGrowth: 16,
      funAndRecreation: 10,
      homeAndLifestyle: 14,
    },
  },
  {
    date: '2023-11-01',
    label: 'Nov',
    values: {
      career: 22,
      money: 18,
      health: 18,
      loveLife: 15,
      familyAndFriends: 17,
      personalGrowth: 20,
      funAndRecreation: 12,
      homeAndLifestyle: 13,
    },
  },
  {
    date: '2024-01-01',
    label: 'Jan 2024',
    values: {
      career: 18,
      money: 16,
      health: 23,
      loveLife: 17,
      familyAndFriends: 15,
      personalGrowth: 24,
      funAndRecreation: 13,
      homeAndLifestyle: 12,
    },
  },
  {
    date: '2024-03-01',
    label: 'Mar',
    values: {
      career: 16,
      money: 14,
      health: 25,
      loveLife: 20,
      familyAndFriends: 19,
      personalGrowth: 26,
      funAndRecreation: 14,
      homeAndLifestyle: 15,
    },
  },
  {
    date: '2024-05-01',
    label: 'May',
    values: {
      career: 21,
      money: 13,
      health: 21,
      loveLife: 18,
      familyAndFriends: 22,
      personalGrowth: 27,
      funAndRecreation: 16,
      homeAndLifestyle: 17,
    },
  },
  {
    date: '2024-07-01',
    label: 'Jul 2024',
    values: {
      career: 23,
      money: 12,
      health: 20,
      loveLife: 16,
      familyAndFriends: 24,
      personalGrowth: 29,
      funAndRecreation: 18,
      homeAndLifestyle: 19,
    },
  },
];

const themeKeys = Object.keys(themeRegistry) as ThemeKey[];

export function LandingJourneyPreview() {
  return (
    <div className="radius-card border-border bg-card space-y-6 border p-6">
      <ul
        aria-label="Life themes"
        className="flex flex-wrap items-center gap-x-6 gap-y-3"
      >
        {themeKeys.map((key) => (
          <li className="flex items-center gap-2" key={key}>
            <span
              aria-hidden="true"
              className="radius-pill size-3"
              style={{ background: themeRegistry[key].color }}
            />
            <Typography className="text-muted-foreground" variant="bodySmall">
              {themeRegistry[key].label}
            </Typography>
          </li>
        ))}
      </ul>
      <div className="overflow-x-auto">
        <div className="min-w-[720px]">
          <JourneySteamgraph
            points={journeyPoints}
            title="Relative presence of eight life themes from September 2023 to July 2024"
          />
        </div>
      </div>
      <Typography
        className="text-muted-foreground text-center"
        variant="bodySmall"
      >
        Theme size represents its relative presence in your entries.
      </Typography>
      <Typography
        as="blockquote"
        className="text-muted-foreground text-center"
        variant="journalExcerpt"
      >
        “The journey becomes available only after enough evidence exists across
        time.”
      </Typography>
    </div>
  );
}
