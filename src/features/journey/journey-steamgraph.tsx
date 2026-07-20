import { Typography } from '@/components/design-system';
import { themeRegistry, type ThemeKey } from '@/config/design-system';

import type { JourneySteamPoint } from './model';

const themeKeys = Object.keys(themeRegistry) as ThemeKey[];

interface PlotPoint {
  x: number;
  y: number;
}

function curve(points: PlotPoint[], move = true) {
  if (points.length === 0) return '';
  const commands = move ? [`M ${points[0]!.x} ${points[0]!.y}`] : [];
  for (let index = 0; index < points.length - 1; index += 1) {
    const point = points[index]!;
    const next = points[index + 1]!;
    const controlX = (point.x + next.x) / 2;
    commands.push(
      `C ${controlX} ${point.y} ${controlX} ${next.y} ${next.x} ${next.y}`,
    );
  }
  return commands.join(' ');
}

function streamPath(
  points: JourneySteamPoint[],
  key: ThemeKey,
  priorKeys: ThemeKey[],
  scale: number,
) {
  const top = points.map((point, index) => {
    const x = (index / Math.max(1, points.length - 1)) * 1000;
    const total = themeKeys.reduce(
      (sum, themeKey) => sum + point.values[themeKey],
      0,
    );
    const offset = 110 - (total * scale) / 2;
    const prior = priorKeys.reduce(
      (sum, priorKey) => sum + point.values[priorKey],
      0,
    );
    return { x, y: offset + prior * scale };
  });
  const bottom = points.map((point, index) => {
    const x = (index / Math.max(1, points.length - 1)) * 1000;
    const total = themeKeys.reduce(
      (sum, themeKey) => sum + point.values[themeKey],
      0,
    );
    const offset = 110 - (total * scale) / 2;
    const prior = priorKeys.reduce(
      (sum, priorKey) => sum + point.values[priorKey],
      0,
    );
    return { x, y: offset + (prior + point.values[key]) * scale };
  });
  const reversedBottom = [...bottom].reverse();
  return `${curve(top)} L ${reversedBottom[0]!.x} ${reversedBottom[0]!.y} ${curve(reversedBottom, false)} Z`;
}

export interface JourneySteamgraphProps {
  points: JourneySteamPoint[];
  muted?: boolean;
  title: string;
}

export function JourneySteamgraph({
  muted = false,
  points,
  title,
}: JourneySteamgraphProps) {
  const maximumTotal = Math.max(
    1,
    ...points.map((point) =>
      themeKeys.reduce((sum, key) => sum + point.values[key], 0),
    ),
  );
  const scale = 176 / maximumTotal;

  return (
    <figure className="w-full max-w-full min-w-0 overflow-hidden">
      <div className="w-full min-w-0">
        <svg
          aria-label={title}
          className="steamgraph-height w-full"
          preserveAspectRatio="none"
          role="img"
          viewBox="0 0 1000 220"
        >
          {points.slice(1, -1).map((point, index) => {
            const x = ((index + 1) / Math.max(1, points.length - 1)) * 1000;
            return (
              <line
                key={point.date}
                stroke="var(--border)"
                strokeDasharray="4 5"
                x1={x}
                x2={x}
                y1="8"
                y2="212"
              />
            );
          })}
          {themeKeys.map((key, index) => (
            <path
              d={streamPath(points, key, themeKeys.slice(0, index), scale)}
              fill={
                muted ? 'var(--muted-foreground)' : themeRegistry[key].color
              }
              key={key}
              opacity={muted ? 0.08 + index * 0.012 : 0.78}
              stroke={muted ? 'var(--border)' : themeRegistry[key].color}
              strokeWidth="1"
            />
          ))}
        </svg>
        <div aria-hidden="true" className="grid grid-cols-6 gap-2 pt-3">
          {points.map((point) => (
            <Typography
              className="text-muted-foreground text-center"
              key={point.date}
              variant="bodySmall"
            >
              {point.label}
            </Typography>
          ))}
        </div>
      </div>
      <figcaption className="sr-only">{title}</figcaption>
      <div className="sr-only overflow-hidden">
        <table>
          <caption>{title} data</caption>
          <thead>
            <tr>
              <th scope="col">Period</th>
              {themeKeys.map((key) => (
                <th key={key} scope="col">
                  {themeRegistry[key].label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.date}>
                <th scope="row">{point.label}</th>
                {themeKeys.map((key) => (
                  <td key={key}>{point.values[key]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
