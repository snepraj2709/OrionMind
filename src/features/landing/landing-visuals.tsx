import Image from 'next/image';

import { Typography } from '@/components/design-system';
import { themeRegistry, type ThemeKey } from '@/config/design-system';

import styles from './landing.module.css';

interface LandingMockImageProps {
  alt: string;
  fileName: string;
  height: number;
  priority?: boolean;
  width: number;
}

function LandingMockImage({
  alt,
  fileName,
  height,
  priority = true,
  width,
}: LandingMockImageProps) {
  return (
    <Image
      alt={alt}
      className={styles.mockImage}
      height={height}
      priority={priority}
      sizes={`(min-width: 1024px) ${width}px, 100vw`}
      src={`/images/landing/${fileName}.png`}
      width={width}
    />
  );
}

export function LandingThoughtNetwork() {
  return (
    <LandingMockImage
      alt=""
      fileName="hero"
      height={420}
      priority
      width={624}
    />
  );
}

export function LandingCapturePreview() {
  return (
    <LandingMockImage
      alt='Recording Thought. "Capture first. Structure comes later."'
      fileName="capture"
      height={380}
      width={733}
    />
  );
}

export function LandingReviewPreview() {
  return (
    <LandingMockImage
      alt="Review Extracted Insights with three proposed reflections, ideas and memories."
      fileName="review"
      height={400}
      width={733}
    />
  );
}

export function LandingInsightsPreview() {
  return (
    <LandingMockImage
      alt="Recurring themes, connected memories, total approved reflections and system status."
      fileName="insights"
      height={320}
      width={1280}
    />
  );
}

export function LandingHiddenDriverPreview() {
  return (
    <LandingMockImage
      alt="A Hidden Driver reflection with evidence and three response choices."
      fileName="hidden-driver"
      height={360}
      width={624}
    />
  );
}

export function LandingRecurringLoopOrbital() {
  return (
    <LandingMockImage
      alt="A recurring avoidance loop: overwhelm, postpone, temporary relief, issue escalates, guilt and anxiety, reduced capacity, and avoidance repeats."
      fileName="recurring-loop"
      height={460}
      width={560}
    />
  );
}

export function LandingInnerTensionPreview() {
  return (
    <LandingMockImage
      alt="Inner tensions between achievement and rest, and between belonging and authenticity."
      fileName="inner-tensions"
      height={360}
      width={624}
    />
  );
}

const journeyLabels = [
  'Sep 2023',
  'Oct',
  'Nov 2023',
  'Dec',
  'Jan 2024',
  'Feb',
  'Mar 2024',
  'Apr',
  'May 2024',
  'Jul 2024',
] as const;

const themeKeys = Object.keys(themeRegistry) as ThemeKey[];

const landingThemeLabels: Record<ThemeKey, string> = {
  career: 'Career',
  money: 'Money',
  health: 'Health',
  loveLife: 'Love Life',
  familyAndFriends: 'Family & Friends',
  personalGrowth: 'Personal Growth',
  funAndRecreation: 'Fun & Recreation',
  homeAndLifestyle: 'Home & Lifestyle',
};

export function LandingJourneyLegend() {
  return (
    <ul aria-label="Life themes" className={styles.journeyLegend}>
      {themeKeys.map((key) => (
        <li key={key}>
          <span
            aria-hidden="true"
            style={{ backgroundColor: themeRegistry[key].color }}
          />
          <Typography className="type-landing-caption" variant="bodySmall">
            {landingThemeLabels[key]}
          </Typography>
        </li>
      ))}
    </ul>
  );
}

export function LandingJourneyPreview() {
  const title =
    'Relative presence of eight life themes from September 2023 to July 2024';

  return (
    <div className={styles.journeyPreview}>
      <LandingMockImage
        alt={title}
        fileName="journey"
        height={420}
        width={1280}
      />
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
            {journeyLabels.map((label) => (
              <tr key={label}>
                <th scope="row">{label}</th>
                {themeKeys.map((key) => (
                  <td key={key}>Shown in the journey chart</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Typography className="sr-only" variant="bodySmall">
        Theme size represents its relative presence in your entries. The journey
        becomes available only after enough evidence exists across time.
      </Typography>
    </div>
  );
}
