import { ArrowRight, Check, ShieldCheck } from 'lucide-react';
import Link from 'next/link';
import type { ReactNode } from 'react';

import { AppButton, Typography } from '@/components/design-system';
import { BrandMark, MobileNavigation, PageShell } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { routes } from '@/config/routes';
import { cn } from '@/lib/utils';

import styles from './landing.module.css';
import {
  LandingCapturePreview,
  LandingHiddenDriverPreview,
  LandingInnerTensionPreview,
  LandingInsightsPreview,
  LandingJourneyPreview,
  LandingRecurringLoopOrbital,
  LandingReviewPreview,
  LandingThoughtNetwork,
} from './landing-visuals';

const publicNavigation = [
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Reflections', href: '#reflections' },
  { label: 'Journey', href: '#journey' },
  { label: 'Privacy', href: '#privacy' },
] as const;

const productJourney = [
  {
    number: '01',
    title: 'Capture',
    description: 'Write or speak freely, without organizing the thought first.',
  },
  {
    number: '02',
    title: 'Review',
    description: 'Approve what feels accurate and reject what does not.',
  },
  {
    number: '03',
    title: 'Insights',
    description: 'See ideas, memories and reflections beside their source.',
  },
  {
    number: '04',
    title: 'Reflections',
    description: 'Notice patterns only after repeated evidence exists.',
  },
] as const;

const trustPrinciples = [
  {
    title: 'Private by intention',
    description:
      'Design the experience around sensitive personal writing. Your data is yours alone, built with absolute cryptographic separation.',
  },
  {
    title: 'You approve the information',
    description:
      'Extracted items do not automatically become accepted insights. You curate the timeline of your own mind.',
  },
  {
    title: 'Evidence remains visible',
    description:
      'Patterns can be traced back to supporting entries. You will always know why a trend was proposed.',
  },
  {
    title: 'Nothing is presented as diagnosis',
    description:
      'Orion supports reflection rather than replacing professional care or personal judgment. No labels, no boxes.',
  },
] as const;

interface LandingSectionHeaderProps {
  eyebrow: string;
  title: string;
  description?: string;
  id: string;
  centered?: boolean;
}

function LandingSectionHeader({
  centered = false,
  description,
  eyebrow,
  id,
  title,
}: LandingSectionHeaderProps) {
  return (
    <div
      className={cn(
        'text-measure space-y-4',
        centered && 'mx-auto text-center',
      )}
    >
      <Typography className="text-accent" variant="eyebrow">
        {eyebrow}
      </Typography>
      <Typography as="h2" id={id} variant="pageTitle">
        {title}
      </Typography>
      {description ? (
        <Typography className="text-muted-foreground" variant="body">
          {description}
        </Typography>
      ) : null}
    </div>
  );
}

interface LandingFeatureSectionProps {
  actions?: ReactNode;
  bullets?: readonly string[];
  description: string;
  eyebrow: string;
  id: string;
  title: string;
  visual: ReactNode;
  visualFirst?: boolean;
  surface?: boolean;
}

function LandingFeatureSection({
  actions,
  bullets,
  description,
  eyebrow,
  id,
  surface = false,
  title,
  visual,
  visualFirst = false,
}: LandingFeatureSectionProps) {
  return (
    <section
      aria-labelledby={`${id}-title`}
      className={cn(
        styles.sectionAnchor,
        'border-border border-t',
        surface && 'bg-card',
      )}
      id={id}
    >
      <PageShell
        as="div"
        className="sidebar:grid-cols-2 sidebar:gap-16 grid items-center gap-10 py-20"
      >
        <div className={cn('min-w-0', visualFirst && 'sidebar:order-first')}>
          {visual}
        </div>
        <div
          className={cn(
            'text-measure space-y-6',
            visualFirst && 'sidebar:-order-1',
          )}
        >
          <div className="space-y-4">
            <Typography className="text-accent" variant="eyebrow">
              {eyebrow}
            </Typography>
            <Typography as="h2" id={`${id}-title`} variant="pageTitle">
              {title}
            </Typography>
            <Typography className="text-muted-foreground" variant="body">
              {description}
            </Typography>
          </div>
          {bullets ? (
            <ul className="space-y-3">
              {bullets.map((bullet) => (
                <li className="flex items-start gap-3" key={bullet}>
                  <Check
                    aria-hidden="true"
                    className="text-accent mt-1 size-5 shrink-0"
                  />
                  <Typography variant="bodySmall">{bullet}</Typography>
                </li>
              ))}
            </ul>
          ) : null}
          {actions}
        </div>
      </PageShell>
    </section>
  );
}

function LandingDesktopHeader() {
  return (
    <header className="border-border bg-card sidebar:block sticky top-0 z-40 hidden border-b">
      <PageShell
        as="div"
        className="flex items-center justify-between gap-6 py-3"
      >
        <BrandMark />
        <nav aria-label="Landing page" className="flex items-center gap-4">
          {publicNavigation.map((item) => (
            <AppLink
              className="type-navigation px-2"
              href={item.href}
              key={item.href}
            >
              {item.label}
            </AppLink>
          ))}
        </nav>
        <nav aria-label="Account" className="flex items-center gap-3">
          <AppLink className="type-navigation px-2" href={routes.login.path}>
            Sign in
          </AppLink>
          <AppButton asChild>
            <Link href={routes.signup.path}>Start reflecting</Link>
          </AppButton>
        </nav>
      </PageShell>
    </header>
  );
}

function LandingMobileHeader() {
  return (
    <MobileNavigation
      brand={<BrandMark />}
      className="bg-card sidebar:hidden"
      description="Explore Orion or begin reflecting"
      footer={
        <AppButton asChild className="w-full">
          <Link href={routes.signup.path}>Start reflecting</Link>
        </AppButton>
      }
      utility={
        <AppLink className="type-navigation px-2" href={routes.login.path}>
          Sign in
        </AppLink>
      }
    >
      <div className="flex flex-col gap-2">
        {publicNavigation.map((item) => (
          <AppLink
            className="type-navigation px-3 py-3"
            href={item.href}
            key={item.href}
          >
            {item.label}
          </AppLink>
        ))}
      </div>
    </MobileNavigation>
  );
}

function LandingHeroHeadline() {
  const words = ['Connect', 'the', 'dots', 'in', 'your', 'thoughts.'];

  return (
    <Typography as="h1" id="hero-title" variant="display">
      <span className="sr-only">Connect the dots in your thoughts.</span>
      <span aria-hidden="true" className="flex flex-wrap gap-x-3">
        {words.map((word, index) => (
          <span className={styles.heroWord} key={word}>
            <span data-hero-word style={{ animationDelay: `${index * 90}ms` }}>
              {word}
            </span>
          </span>
        ))}
      </span>
    </Typography>
  );
}

export function LandingPage() {
  return (
    <div className="bg-background text-foreground min-h-screen overflow-x-hidden">
      <LandingDesktopHeader />
      <LandingMobileHeader />

      <main id="main-content">
        <section
          aria-labelledby="hero-title"
          className="flex min-h-svh items-center"
        >
          <PageShell
            as="div"
            className="sidebar:grid-cols-2 sidebar:gap-16 grid w-full items-center gap-10 py-20"
          >
            <div className="text-measure space-y-6">
              <LandingHeroHeadline />
              <Typography className="text-muted-foreground" variant="bodyLarge">
                Orion helps you record what is on your mind, notice what keeps
                coming back and understand the patterns shaping your life over
                time.
              </Typography>
              <div className="flex flex-wrap items-center gap-4">
                <AppButton asChild>
                  <Link href={routes.signup.path}>Start reflecting</Link>
                </AppButton>
                <AppButton asChild variant="outline">
                  <AppLink href="#how-it-works">See how it works</AppLink>
                </AppButton>
              </div>
              <Typography className="text-muted-foreground" variant="bodySmall">
                Private by design. Your thoughts remain yours.
              </Typography>
            </div>
            <LandingThoughtNetwork />
          </PageShell>
        </section>

        <section
          aria-label="Carl Jung quotation"
          className="border-border bg-card border-y"
        >
          <PageShell as="div" className="py-20 text-center">
            <Typography
              as="blockquote"
              className="text-measure mx-auto"
              variant="reflectiveStatement"
            >
              “Until you make the unconscious conscious, it will direct your
              life and you will call it fate.”
            </Typography>
            <Typography
              className="text-muted-foreground mt-4"
              variant="metadata"
            >
              Carl Jung
            </Typography>
          </PageShell>
        </section>

        <section
          aria-labelledby="how-it-works-title"
          className={cn(styles.sectionAnchor, 'border-border border-b')}
          id="how-it-works"
        >
          <PageShell as="div" className="space-y-12 py-20">
            <LandingSectionHeader
              description="Orion turns isolated entries into a connected view of your inner world while keeping you in control at every stage."
              eyebrow="How it works"
              id="how-it-works-title"
              title="From a passing thought to a visible pattern."
            />
            <ol className="sidebar:grid-cols-4 grid gap-6 sm:grid-cols-2">
              {productJourney.map((stage) => (
                <li
                  className="border-border space-y-3 border-t pt-4"
                  key={stage.number}
                >
                  <Typography className="text-accent" variant="eyebrow">
                    {stage.number}
                  </Typography>
                  <Typography as="h3" variant="componentTitle">
                    {stage.title}
                  </Typography>
                  <Typography
                    className="text-muted-foreground"
                    variant="bodySmall"
                  >
                    {stage.description}
                  </Typography>
                </li>
              ))}
            </ol>
          </PageShell>
        </section>

        <LandingFeatureSection
          actions={
            <AppButton asChild variant="link">
              <Link href={routes.newEntry.path}>
                Write your first entry
                <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
            </AppButton>
          }
          bullets={[
            'Write in your own words',
            'Speak instead of typing',
            'Return to unfinished thoughts',
          ]}
          description="Write freely about what happened, what is worrying you or what you want to remember. You do not need to organize it first."
          eyebrow="Capture"
          id="capture"
          title="Start with what is already in your mind."
          visual={<LandingCapturePreview />}
          visualFirst
        />

        <LandingFeatureSection
          actions={
            <AppButton asChild variant="link">
              <AppLink href="#reflections">
                See how reflection works
                <ArrowRight aria-hidden="true" className="size-4" />
              </AppLink>
            </AppButton>
          }
          bullets={[
            'Approve what feels accurate',
            'Reject what does not resonate',
            'Keep every suggestion connected to its source',
          ]}
          description="Orion may identify ideas, memories and possible insights inside an entry. Nothing is accepted automatically. You review every suggestion."
          eyebrow="Review"
          id="review"
          surface
          title="You decide what becomes part of your story."
          visual={<LandingReviewPreview />}
        />

        <section
          aria-labelledby="insights-title"
          className={cn(styles.sectionAnchor, 'border-border border-t')}
          id="insights"
        >
          <PageShell as="div" className="space-y-10 py-20">
            <div className="sidebar:grid-cols-2 sidebar:gap-16 grid gap-8">
              <LandingSectionHeader
                eyebrow="Insights"
                id="insights-title"
                title="See your thoughts beside each other."
              />
              <Typography className="text-muted-foreground" variant="body">
                Entries that once felt separate begin to form visible clusters.
                Ideas, memories and reflections remain connected to the words
                that produced them.
              </Typography>
            </div>
            <LandingInsightsPreview />
          </PageShell>
        </section>

        <section
          aria-labelledby="reflections-title"
          className={cn(styles.sectionAnchor, 'border-border bg-card border-y')}
          id="reflections"
        >
          <PageShell as="div" className="space-y-10 py-20 text-center">
            <LandingSectionHeader
              centered
              description="After enough approved history exists, Orion can propose reflective views designed to help you notice what may be operating beneath the surface."
              eyebrow="Reflections"
              id="reflections-title"
              title="Patterns appear slowly, across repeated evidence rather than a single moment."
            />
            <div className="border-border mx-auto flex max-w-fit flex-wrap justify-center gap-2 border-b pb-3">
              {['Hidden Drivers', 'Recurring Loops', 'Inner Tensions'].map(
                (label, index) => (
                  <span
                    className={cn(
                      'radius-control type-navigation px-4 py-3',
                      index === 0
                        ? 'bg-secondary text-primary'
                        : 'text-muted-foreground',
                    )}
                    key={label}
                  >
                    {label}
                  </span>
                ),
              )}
            </div>
          </PageShell>
        </section>

        <LandingFeatureSection
          description="A hidden driver is a recurring need or fear that may be influencing several different situations. Orion proposes one only when related evidence appears across time."
          eyebrow="Hidden Drivers"
          id="hidden-drivers"
          title="Notice the hopes that keep repeating."
          visual={<LandingHiddenDriverPreview />}
          visualFirst
        />

        <LandingFeatureSection
          description="Some difficulties are not isolated events. They are cycles in which one reaction creates the conditions for the next."
          eyebrow="Recurring Loops"
          id="recurring-loops"
          surface
          title="Notice how one response turns into another."
          visual={<LandingRecurringLoopOrbital />}
        />

        <LandingFeatureSection
          description="Some decisions feel difficult because two important needs are pulling in different directions. Seeing both can make room for a more honest integration."
          eyebrow="Inner Tensions"
          id="inner-tensions"
          title="Understand the needs you are trying to hold at once."
          visual={<LandingInnerTensionPreview />}
          visualFirst
        />

        <section
          aria-labelledby="journey-title"
          className={cn(styles.sectionAnchor, 'border-border bg-card border-y')}
          id="journey"
        >
          <PageShell as="div" className="space-y-10 py-20">
            <LandingSectionHeader
              description="Individual entries capture moments. Journey reveals how the relative weight of important life themes changes across months and years."
              eyebrow="Journey"
              id="journey-title"
              title="See what has occupied your life over time."
            />
            <LandingJourneyPreview />
            <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
              <Typography
                className="text-muted-foreground text-measure"
                variant="bodySmall"
              >
                Orion does not manufacture a life story from one entry. The
                journey unfolds organically over months of active reflection.
              </Typography>
              <AppButton asChild>
                <Link href={routes.signup.path}>Begin your journey</Link>
              </AppButton>
            </div>
          </PageShell>
        </section>

        <section
          aria-labelledby="privacy-title"
          className={cn(styles.sectionAnchor, 'border-border border-b')}
          id="privacy"
        >
          <PageShell as="div" className="space-y-12 py-20">
            <div className="flex items-start gap-4">
              <ShieldCheck
                aria-hidden="true"
                className="text-primary size-8 shrink-0"
              />
              <LandingSectionHeader
                eyebrow="Trust & Privacy"
                id="privacy-title"
                title="Reflection without surrendering authority."
              />
            </div>
            <div className="grid gap-6 md:grid-cols-2">
              {trustPrinciples.map((principle) => (
                <article
                  className="radius-card border-border bg-card space-y-4 border p-6"
                  key={principle.title}
                >
                  <Typography as="h3" variant="componentTitle">
                    {principle.title}
                  </Typography>
                  <Typography
                    className="text-muted-foreground"
                    variant="bodySmall"
                  >
                    {principle.description}
                  </Typography>
                </article>
              ))}
            </div>
          </PageShell>
        </section>

        <section aria-labelledby="final-cta-title" className="bg-background">
          <PageShell as="div" className="py-20 text-center">
            <div className="text-measure mx-auto space-y-6">
              <Typography as="h2" id="final-cta-title" variant="display">
                Make your thinking visible.
              </Typography>
              <Typography className="text-muted-foreground" variant="body">
                Begin with one thought. Over time, Orion helps you see what
                keeps returning, what is changing and what may have been guiding
                you unnoticed.
              </Typography>
              <div className="flex flex-wrap items-center justify-center gap-4">
                <AppButton asChild>
                  <Link href={routes.signup.path}>Start reflecting</Link>
                </AppButton>
                <AppLink
                  className="type-navigation px-2"
                  href={routes.login.path}
                >
                  Sign in
                </AppLink>
              </div>
              <Typography
                className="text-muted-foreground"
                variant="journalExcerpt"
              >
                Your first entry can be as unfinished as your thoughts.
              </Typography>
            </div>
          </PageShell>
        </section>
      </main>

      <footer className="border-border bg-card border-t">
        <PageShell as="div" className="space-y-10 py-12">
          <div className="flex flex-col gap-8 md:flex-row md:items-center md:justify-between">
            <BrandMark />
            <nav
              aria-label="Footer navigation"
              className="flex flex-wrap items-center gap-4"
            >
              <AppLink className="type-metadata px-2" href="#how-it-works">
                How it works
              </AppLink>
              <AppLink className="type-metadata px-2" href="#privacy">
                Privacy
              </AppLink>
              <Typography
                className="text-muted-foreground px-2"
                variant="metadata"
              >
                Terms
              </Typography>
              <AppLink className="type-metadata px-2" href={routes.login.path}>
                Sign in
              </AppLink>
              <AppLink className="type-metadata px-2" href={routes.signup.path}>
                Start reflecting
              </AppLink>
            </nav>
          </div>
          <div className="border-border flex flex-col gap-4 border-t pt-6 md:flex-row md:items-center md:justify-between">
            <Typography className="text-muted-foreground" variant="bodySmall">
              A private space for seeing how your inner world changes over time.
            </Typography>
            <Typography className="text-muted-foreground" variant="bodySmall">
              © 2025 Orion. All rights reserved.
            </Typography>
          </div>
        </PageShell>
      </footer>
    </div>
  );
}
