import type { Metadata } from 'next';
import Link from 'next/link';
import {
  AudioLines,
  BatteryMedium,
  BookOpenText,
  RefreshCw,
} from 'lucide-react';

import {
  EntryCard,
  InsightCard,
  ReflectionCard,
  Surface,
} from '@/components/cards';
import { StatusBadge, ThemeBadge } from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import {
  BrandMark,
  ContentGrid,
  PageShell,
  Section,
} from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { routes } from '@/config/routes';

export const metadata: Metadata = {
  title: 'Reflect with clarity',
  description:
    'Orion is a private space to capture your thoughts, understand recurring patterns, and reflect with greater clarity.',
};

const benefits = [
  {
    title: 'Capture thoughts naturally',
    description:
      'Write what is on your mind, or speak when your thoughts are easier to say aloud.',
    icon: AudioLines,
  },
  {
    title: 'See what keeps returning',
    description:
      'Bring recurring themes and patterns into view without turning reflection into a scorecard.',
    icon: RefreshCw,
  },
  {
    title: 'Learn from your energy',
    description:
      'Notice what adds energy, what drains it, and what those moments reveal about you.',
    icon: BatteryMedium,
  },
] as const;

export default function HomePage() {
  return (
    <div className="bg-background text-foreground min-h-screen">
      <header className="border-border border-b">
        <PageShell
          as="div"
          className="flex flex-wrap items-center justify-between gap-2 py-4"
        >
          <BrandMark />
          <nav aria-label="Account" className="flex items-center gap-2">
            <AppLink className="type-navigation px-2" href={routes.login.path}>
              Log in
            </AppLink>
            <AppButton asChild>
              <Link href={routes.signup.path}>Create Account</Link>
            </AppButton>
          </nav>
        </PageShell>
      </header>

      <main id="main-content">
        <PageShell className="space-y-20">
          <section aria-labelledby="hero-title">
            <ContentGrid columns="editorial" className="items-center gap-10">
              <div className="text-measure space-y-6">
                <Typography className="text-primary" variant="eyebrow">
                  A private place to think
                </Typography>
                <Typography as="h1" id="hero-title" variant="display">
                  Make space for the thoughts that shape you.
                </Typography>
                <Typography
                  className="text-muted-foreground"
                  variant="bodyLarge"
                >
                  Orion helps you capture what is on your mind, notice what
                  returns, and understand yourself with more clarity over time.
                </Typography>
                <div className="flex flex-wrap items-center gap-3">
                  <AppButton asChild>
                    <Link href={routes.signup.path}>Create Account</Link>
                  </AppButton>
                  <AppButton asChild variant="secondary">
                    <Link href={routes.login.path}>Log in</Link>
                  </AppButton>
                </div>
              </div>

              <ReflectionCard
                statement="Notice what returns. Name what matters. Choose with greater clarity."
                supportingText="A quiet record of your words becomes a clearer view of the life underneath them."
              />
            </ContentGrid>
          </section>

          <Section
            description="A simple practice for capturing experience and turning it into useful self-knowledge."
            headingId="benefits-title"
            title="Reflection that stays grounded in your words"
          >
            <ContentGrid columns="three">
              {benefits.map((benefit) => {
                const Icon = benefit.icon;

                return (
                  <Surface className="gap-4 p-6" key={benefit.title}>
                    <div className="radius-control bg-secondary text-primary flex size-10 items-center justify-center">
                      <Icon aria-hidden="true" className="icon-md" />
                    </div>
                    <div className="space-y-2">
                      <Typography as="h3" variant="componentTitle">
                        {benefit.title}
                      </Typography>
                      <Typography
                        className="text-muted-foreground"
                        variant="body"
                      >
                        {benefit.description}
                      </Typography>
                    </div>
                  </Surface>
                );
              })}
            </ContentGrid>
          </Section>

          <Section
            description="Your entries remain at the center. Orion organizes the signals around them without losing the original context."
            headingId="preview-title"
            title="From a passing thought to a clearer pattern"
          >
            <ContentGrid columns="editorial">
              <EntryCard
                excerpt="I felt most like myself during the unhurried part of the morning, before I began responding to everyone else."
                metadata="Tuesday morning · Voice entry"
                status={<StatusBadge label="Captured" variant="success" />}
                title="Today’s entry"
              />
              <InsightCard
                evidence={
                  <span className="flex flex-wrap items-center gap-2">
                    <BookOpenText aria-hidden="true" className="size-4" />
                    <span>Seen across four recent entries</span>
                  </span>
                }
                insight="Quiet, self-directed time consistently restores your energy."
                title="A pattern taking shape"
                actions={<ThemeBadge theme="personalGrowth" />}
              />
            </ContentGrid>
          </Section>

          <section aria-labelledby="final-cta-title">
            <Surface
              className="items-start gap-6 p-8 md:flex-row md:items-center md:justify-between md:p-10"
              variant="muted"
            >
              <div className="text-measure space-y-2">
                <Typography as="h2" id="final-cta-title" variant="sectionTitle">
                  Begin with the thought that is here now.
                </Typography>
                <Typography className="text-muted-foreground" variant="body">
                  Create a private place to return to your own words and see
                  what they reveal over time.
                </Typography>
              </div>
              <AppButton asChild>
                <Link href={routes.signup.path}>Create Account</Link>
              </AppButton>
            </Surface>
          </section>
        </PageShell>
      </main>

      <footer className="border-border border-t">
        <PageShell
          as="div"
          className="flex flex-col gap-2 py-6 md:flex-row md:items-center md:justify-between"
        >
          <Typography variant="metadata">Orion</Typography>
          <Typography className="text-muted-foreground" variant="bodySmall">
            A private place for reflection and self-knowledge.
          </Typography>
        </PageShell>
      </footer>
    </div>
  );
}
