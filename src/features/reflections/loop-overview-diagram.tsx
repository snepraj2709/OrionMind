import { RotateCw } from 'lucide-react';

import { Typography } from '@/components/design-system';

export function LoopOverviewDiagram() {
  return (
    <figure className="flex h-full flex-col items-center justify-center gap-4">
      <Typography as="h3" className="self-start" variant="body">
        The loop at a glance
      </Typography>
      <svg
        aria-hidden="true"
        className="text-primary w-full"
        role="img"
        viewBox="0 0 300 260"
      >
        <defs>
          <marker
            id="loop-arrow"
            markerHeight="6"
            markerWidth="6"
            orient="auto"
            refX="5"
            refY="3"
          >
            <path d="M0,0 L6,3 L0,6 Z" fill="currentColor" />
          </marker>
        </defs>
        <circle
          cx="150"
          cy="130"
          fill="none"
          r="92"
          stroke="currentColor"
          strokeDasharray="5 6"
          strokeWidth="1.5"
        />
        {[
          [150, 38],
          [230, 84],
          [230, 176],
          [150, 222],
          [70, 176],
          [70, 84],
        ].map(([x, y], index) => (
          <g key={index}>
            <circle
              cx={x}
              cy={y}
              fill="var(--card)"
              r="22"
              stroke="var(--border)"
            />
            <text
              className="fill-foreground"
              dominantBaseline="middle"
              textAnchor="middle"
              x={x}
              y={y}
            >
              {index + 1}
            </text>
          </g>
        ))}
        <path
          d="M83 66 A92 92 0 0 1 123 43"
          fill="none"
          markerEnd="url(#loop-arrow)"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <text
          className="fill-primary"
          dominantBaseline="middle"
          textAnchor="middle"
          x="150"
          y="122"
        >
          LOOP
        </text>
        <text
          className="fill-primary"
          dominantBaseline="middle"
          textAnchor="middle"
          x="150"
          y="144"
        >
          repeats
        </text>
      </svg>
      <figcaption className="text-primary flex items-center gap-3">
        <RotateCw aria-hidden="true" className="size-5" />
        <Typography variant="bodySmall">Step 6 returns to step 1</Typography>
      </figcaption>
    </figure>
  );
}
