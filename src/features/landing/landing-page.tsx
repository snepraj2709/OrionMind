import { ArrowRight } from 'lucide-react';
import Image from 'next/image';
import Link from 'next/link';
import type { ReactNode } from 'react';

import { AppButton, Typography } from '@/components/design-system';
import { MobileNavigation, PageShell } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { routes } from '@/config/routes';
import { cn } from '@/lib/utils';

import styles from './landing.module.css';
import {
  LandingCapturePreview,
  LandingHiddenDriverPreview,
  LandingInnerTensionPreview,
  LandingInsightsPreview,
  LandingJourneyLegend,
  LandingJourneyPreview,
  LandingRecurringLoopOrbital,
  LandingReviewPreview,
  LandingThoughtNetwork,
} from './landing-visuals';

const publicNavigation = [
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Insights', href: '#insights' },
  { label: 'Reflections', href: '#reflections' },
  { label: 'Journey', href: '#journey' },
] as const;

const reflectionTabs = [
  { label: 'Hidden drivers', href: '#hidden-drivers' },
  { label: 'Recurring loops', href: '#recurring-loops' },
  { label: 'Inner tensions', href: '#inner-tensions' },
] as const;

const productJourney = [
  {
    dots: 1,
    title: 'Capture',
    description:
      'Write or speak freely without organising your thoughts first.',
  },
  {
    dots: 2,
    title: 'Review',
    description:
      'Approve or dismiss the ideas, memories and reflections Orion extracts.',
  },
  {
    dots: 3,
    title: 'Understand',
    description:
      'See insights, hidden drivers, recurring loops and inner tensions taking shape.',
  },
  {
    dots: 3,
    title: 'Follow your journey',
    description:
      'Notice how the themes occupying your life change over weeks, months and years.',
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
  eyebrow?: string;
  title: string;
  titleClassName?: string;
  description?: string;
  descriptionClassName?: string;
  id: string;
  centered?: boolean;
}

function LandingSectionHeader({
  centered = false,
  description,
  descriptionClassName,
  eyebrow,
  id,
  title,
  titleClassName,
}: LandingSectionHeaderProps) {
  return (
    <div
      className={cn(
        'text-measure space-y-4',
        centered && 'mx-auto text-center',
      )}
    >
      {eyebrow ? (
        <Typography className="text-accent" variant="eyebrow">
          {eyebrow}
        </Typography>
      ) : null}
      <Typography
        as="h2"
        className={titleClassName}
        id={id}
        variant="pageTitle"
      >
        {title}
      </Typography>
      {description ? (
        <Typography
          className={cn('text-muted-foreground', descriptionClassName)}
          variant="body"
        >
          {description}
        </Typography>
      ) : null}
    </div>
  );
}

interface LandingFeatureSectionProps {
  actions?: ReactNode;
  bullets?: readonly string[];
  callout?: ReactNode;
  details?: readonly { description: string; title: string }[];
  description: string;
  eyebrow: string;
  id: string;
  sectionClassName: string;
  title: string;
  titleClassName?: string;
  visual: ReactNode;
  visualFirst?: boolean;
  surface?: boolean;
}

function LandingFeatureSection({
  actions,
  bullets,
  callout,
  details,
  description,
  eyebrow,
  id,
  sectionClassName,
  surface = false,
  title,
  titleClassName,
  visual,
  visualFirst = false,
}: LandingFeatureSectionProps) {
  return (
    <section
      aria-labelledby={`${id}-title`}
      className={cn(
        styles.featureSection,
        sectionClassName,
        'border-border border-t',
        surface && 'bg-card',
      )}
      id={id}
    >
      <PageShell
        as="div"
        className={cn(
          styles.exactShell,
          styles.featureShell,
          'sidebar:grid-cols-2 grid items-center gap-10',
        )}
      >
        <div
          className={cn(
            styles.featureVisual,
            'min-w-0',
            visualFirst && 'sidebar:order-first',
          )}
        >
          {visual}
        </div>
        <div
          className={cn(
            'text-measure space-y-6',
            styles.featureCopy,
            visualFirst && 'sidebar:-order-1',
          )}
        >
          <div className="space-y-4">
            <Typography className="text-accent" variant="eyebrow">
              {eyebrow}
            </Typography>
            <Typography
              as="h2"
              className={cn('type-landing-section', titleClassName)}
              id={`${id}-title`}
              variant="pageTitle"
            >
              {title}
            </Typography>
            <Typography className="text-muted-foreground" variant="body">
              {description}
            </Typography>
          </div>
          {callout}
          {bullets ? (
            <ul className={cn(styles.featureBullets, 'space-y-3')}>
              {bullets.map((bullet) => (
                <li className="flex items-start gap-3" key={bullet}>
                  <span aria-hidden="true" className={styles.bulletDot} />
                  <Typography
                    className="whitespace-pre-line"
                    variant="bodySmall"
                  >
                    {bullet}
                  </Typography>
                </li>
              ))}
            </ul>
          ) : null}
          {details ? (
            <dl className={styles.featureDetails}>
              {details.map((detail) => (
                <div key={detail.title}>
                  <dt>
                    <Typography
                      as="span"
                      className="type-landing-compact"
                      variant="metadata"
                    >
                      {detail.title}
                    </Typography>
                  </dt>
                  <dd>
                    <Typography
                      as="span"
                      className="type-landing-compact text-muted-foreground"
                      variant="bodySmall"
                    >
                      {detail.description}
                    </Typography>
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
          {actions}
        </div>
      </PageShell>
    </section>
  );
}

function LandingBrand() {
  return (
    <AppLink className={styles.landingBrand} href={routes.home.path}>
      <Image
        alt=""
        aria-hidden="true"
        height={28}
        src="/images/light-mode-transparent.svg"
        width={28}
      />
      <Typography
        as="span"
        className="type-landing-brand"
        variant="journalExcerpt"
      >
        Orion
      </Typography>
    </AppLink>
  );
}

function LandingDesktopHeader() {
  return (
    <header
      className={cn(
        styles.desktopHeader,
        'border-border bg-card sidebar:block hidden w-full border-b',
      )}
    >
      <PageShell
        as="div"
        className={cn(
          styles.exactShell,
          styles.headerShell,
          'flex items-center justify-between gap-6',
        )}
      >
        <LandingBrand />
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
      brand={<LandingBrand />}
      className="bg-card sidebar:hidden static"
      description="Explore Orion or begin reflecting"
      footer={
        <AppButton asChild>
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
    <Typography
      as="h1"
      className={cn(styles.heroHeadline, 'type-landing-hero')}
      id="hero-title"
      variant="display"
    >
      <span className="sr-only">Connect the dots in your thoughts.</span>
      <span aria-hidden="true" className="flex flex-wrap gap-x-3">
        {words.map((word, index) => (
          <span className={styles.heroWord} key={word}>
            <span data-hero-word style={{ animationDelay: `${index * 250}ms` }}>
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
    <div
      className={cn(
        styles.landingPage,
        'bg-background text-foreground min-h-screen overflow-x-clip',
      )}
    >
      <LandingDesktopHeader />
      <LandingMobileHeader />

      <main id="main-content">
        <section aria-labelledby="hero-title" className={styles.heroSection}>
          <PageShell
            as="div"
            className={cn(
              styles.exactShell,
              styles.heroShell,
              'sidebar:grid-cols-2 grid w-full items-center gap-10',
            )}
          >
            <div className={cn(styles.heroCopy, 'text-measure space-y-6')}>
              <LandingHeroHeadline />
              <Typography className="text-muted-foreground" variant="bodyLarge">
                Your thoughts leave patterns behind. Orion helps you capture
                them, review what matters and see the hidden forces shaping your
                attention, life choices and sense of self.
              </Typography>
              <div className="flex flex-wrap items-center gap-4">
                <AppButton asChild>
                  <Link href={routes.signup.path}>Start reflecting</Link>
                </AppButton>
                <AppButton asChild variant="link">
                  <AppLink href="#how-it-works">
                    See how Orion works
                    <ArrowRight aria-hidden="true" className="size-4" />
                  </AppLink>
                </AppButton>
              </div>
              <Typography
                className="type-landing-caption text-muted-foreground"
                variant="bodySmall"
              >
                Begin with one thought. No perfect journaling habit required.
              </Typography>
            </div>
            <div className={styles.heroVisual}>
              <LandingThoughtNetwork />
            </div>
          </PageShell>
        </section>

        <section
          aria-label="Carl Jung quotation"
          className={cn(styles.quoteSection, 'border-border bg-card border-y')}
        >
          <PageShell
            as="div"
            className={cn(styles.exactShell, styles.quoteShell, 'text-center')}
          >
            <Typography
              as="blockquote"
              className="type-landing-quote text-measure mx-auto"
              variant="reflectiveStatement"
            >
              &quot;Until you make the unconscious conscious, it will direct
              your life and you will call it fate.&quot;
            </Typography>
            <Typography
              className="text-muted-foreground mt-4"
              variant="metadata"
            >
              — Carl Jung
            </Typography>
            <Typography
              className="type-landing-supporting text-muted-foreground text-measure mx-auto mt-8"
              variant="body"
            >
              Most thoughts disappear as quickly as they arrive. But repeated
              thoughts, emotional reactions and unresolved tensions continue
              influencing what we notice, avoid and choose. Orion gives those
              patterns a place to become visible
            </Typography>
          </PageShell>
        </section>

        <section
          aria-labelledby="how-it-works-title"
          className={cn(styles.transformationSection, 'border-border border-b')}
          id="how-it-works"
        >
          <PageShell
            as="div"
            className={cn(
              styles.exactShell,
              styles.transformationShell,
              'space-y-12',
            )}
          >
            <LandingSectionHeader
              description="Orion turns reflection into a gradual process. You remain in control of what is saved, what feels true and what should be dismissed."
              id="how-it-works-title"
              title="From a passing thought to a visible pattern."
              titleClassName="type-landing-display"
            />
            <ol className="sidebar:grid-cols-4 grid gap-6 sm:grid-cols-2">
              {productJourney.map((stage) => (
                <li className="space-y-3" key={stage.title}>
                  <span aria-hidden="true" className={styles.stageDots}>
                    {Array.from({ length: stage.dots }, (_, index) => (
                      <span key={index} />
                    ))}
                  </span>
                  <Typography
                    as="h3"
                    className="type-landing-stage-title"
                    variant="componentTitle"
                  >
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
                Add your first entry
                <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
            </AppButton>
          }
          bullets={[
            'Voice or text entry',
            'Minimal, distraction-free canvas',
            'No requirement to label or categorise thoughts',
            'Pause, continue or cancel while recording',
          ]}
          description="Speak naturally or write without trying to structure everything first. Orion gives you a quiet space to capture thoughts before they disappear or become simplified by memory."
          eyebrow="CAPTURE"
          id="capture"
          sectionClassName={styles.captureSection}
          title="Start with what is already in your mind."
          titleClassName="type-landing-section-large"
          visual={<LandingCapturePreview />}
          visualFirst
        />

        <LandingFeatureSection
          actions={
            <div className="space-y-4">
              <Typography as="blockquote" variant="journalExcerpt">
                &quot;Orion proposes. You confirm.&quot;
              </Typography>
              <AppButton asChild variant="link">
                <AppLink href="#reflections">
                  See how review works
                  <ArrowRight aria-hidden="true" className="size-4" />
                </AppLink>
              </AppButton>
            </div>
          }
          details={[
            {
              title: 'Ideas',
              description: 'Possibilities worth your attention',
            },
            {
              title: 'Memories',
              description: 'Moments that may matter to you',
            },
            {
              title: 'Reflections',
              description: 'Things you are learning about yourself',
            },
          ]}
          description="Orion extracts possible ideas, memories and reflections from each entry. Nothing is treated as true by default. Review each item, approve what resonates with you and reject which does not."
          eyebrow="REVIEW"
          id="review"
          sectionClassName={styles.reviewSection}
          surface
          title="You decide what becomes part of your story."
          titleClassName="type-landing-section-large"
          visual={<LandingReviewPreview />}
        />

        <section
          aria-labelledby="insights-title"
          className={cn(styles.insightsSection, 'border-border border-t')}
          id="insights"
        >
          <PageShell
            as="div"
            className={cn(
              styles.exactShell,
              styles.insightsShell,
              'space-y-10',
            )}
          >
            <div className="sidebar:grid-cols-2 sidebar:gap-16 grid gap-8">
              <LandingSectionHeader
                description="Once approved, isolated thoughts start forming a complete picture. Orion brings what energized you, drained you, ideas and memories into one place so relationships between them become easier to recognise."
                eyebrow="CONNECT"
                id="insights-title"
                title="See your thoughts beside each other."
                titleClassName="type-landing-section-large"
              />
              <div className="space-y-6">
                <ul className="space-y-3">
                  {[
                    'Revisit ideas before they disappear.',
                    'Preserve memories in your own words.',
                    'Notice what repeatedly energises, drains or teaches you.',
                  ].map((item) => (
                    <li className="flex items-start gap-3" key={item}>
                      <span aria-hidden="true" className={styles.bulletDot} />
                      <Typography variant="bodySmall">{item}</Typography>
                    </li>
                  ))}
                </ul>
                <AppButton asChild variant="link">
                  <AppLink href="#reflections">
                    Explore your insights
                    <ArrowRight aria-hidden="true" className="size-4" />
                  </AppLink>
                </AppButton>
              </div>
            </div>
            <LandingInsightsPreview />
          </PageShell>
        </section>

        <section
          aria-labelledby="reflections-title"
          className={cn(
            styles.reflectionsSection,
            'border-border bg-card border-y',
          )}
          id="reflections"
        >
          <PageShell
            as="div"
            className={cn(
              styles.exactShell,
              styles.reflectionsShell,
              'space-y-10 text-center',
            )}
          >
            <LandingSectionHeader
              centered
              description="Orion looks across multiple entries for repeated signals. These reflections are offered as possibilities to examine, not fixed interpretations or psychological diagnoses."
              id="reflections-title"
              title="Patterns appear when enough moments are placed beside each other."
              titleClassName="type-landing-section-large"
            />
            <div className="border-border mx-auto flex max-w-full flex-nowrap justify-start gap-2 overflow-x-auto border">
              {reflectionTabs.map((item, index) => (
                <AppLink
                  className={cn(
                    'radius-control type-metadata px-4 py-3 whitespace-nowrap',
                    index === 0
                      ? 'bg-secondary text-primary'
                      : 'text-muted-foreground',
                  )}
                  href={item.href}
                  key={item.href}
                >
                  {item.label}
                </AppLink>
              ))}
            </div>
          </PageShell>
        </section>

        <LandingFeatureSection
          actions={
            <div className={styles.hiddenDriverEvidence}>
              <Typography className="text-muted-foreground" variant="bodySmall">
                Orion shows the evidence behind each reflection and lets you
                respond with &quot;This resonates&quot;, &quot;Partly true&quot;
                or &quot;Not true for me.&quot;
              </Typography>
              <div className={styles.emphasis}>
                <span aria-hidden="true" />
                <Typography variant="metadata">
                  Patterns remain hypotheses until you recognise yourself in
                  them.
                </Typography>
              </div>
            </div>
          }
          description="Hidden Drivers surface the needs, environments and forms of activity that repeatedly appear when you feel engaged, capable or energised."
          eyebrow="Hidden Driver"
          id="hidden-drivers"
          sectionClassName={styles.hiddenDriversSection}
          title="See what repeatedly brings you alive."
          visual={<LandingHiddenDriverPreview />}
        />

        <LandingFeatureSection
          callout={
            <Typography
              as="blockquote"
              className="type-landing-editorial"
              variant="journalExcerpt"
            >
              &quot;A loop becomes easier to interrupt once its sequence is
              visible.&quot;
            </Typography>
          }
          bullets={[
            'How the loop unfolds',
            'What the loop may be protecting',
            'A possible way to interrupt it',
            'The entries supporting the pattern',
          ]}
          description="A single difficult day may not reveal much. Repeated sequences across several entries can show how excitement, fragmented attention, insufficient progress and renewed energies reinforce one another."
          eyebrow="Recurring Loop"
          id="recurring-loops"
          sectionClassName={styles.recurringLoopsSection}
          surface
          title="Notice the loops that keep repeating."
          visual={<LandingRecurringLoopOrbital />}
        />

        <LandingFeatureSection
          actions={
            <div className={styles.tensionDetails}>
              <ul>
                <li>
                  <span aria-hidden="true" />
                  <Typography
                    className="type-landing-compact"
                    variant="metadata"
                  >
                    &quot;I need to keep growing&quot; versus &quot;I need space
                    to recover and enjoy my life.&quot;
                  </Typography>
                </li>
                <li>
                  <span aria-hidden="true" />
                  <Typography
                    className="type-landing-compact"
                    variant="metadata"
                  >
                    &quot;I want to be accepted&quot; versus &quot;I want to
                    live and speak according to what feels true to me.&quot;
                  </Typography>
                </li>
              </ul>
              <Typography className="text-muted-foreground" variant="bodySmall">
                Find a possible integration rather than forcing one side to win.
              </Typography>
              <Typography as="blockquote" variant="journalExcerpt">
                &quot;Clarity does not always come from choosing one side.
                Sometimes it comes from seeing both.&quot;
              </Typography>
            </div>
          }
          description="Internal conflicts are not contradictions to eliminate. They are legitimate needs trying to pull you in different directions."
          eyebrow="INNER Tension"
          id="inner-tensions"
          sectionClassName={styles.innerTensionsSection}
          title="Understand the needs you are trying to hold at once."
          visual={<LandingInnerTensionPreview />}
        />

        <section
          aria-labelledby="journey-title"
          className={cn(
            styles.journeySection,
            'border-border bg-card border-y',
          )}
          id="journey"
        >
          <PageShell
            as="div"
            className={cn(styles.exactShell, styles.journeyShell, 'space-y-10')}
          >
            <LandingSectionHeader
              description="Individual entries capture moments. Journey reveals how the relative weight of important life themes changes across months and years."
              eyebrow="Journey"
              id="journey-title"
              title="See what has occupied your life over time."
              titleClassName="type-landing-section-large"
            />
            <LandingJourneyLegend />
            <LandingJourneyPreview />
            <div
              className={cn(
                styles.journeyFooter,
                'flex flex-col gap-6 md:flex-row md:items-center md:justify-between',
              )}
            >
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
          className={cn(styles.trustSection, 'border-border border-b')}
          id="privacy"
        >
          <PageShell
            as="div"
            className={cn(styles.exactShell, styles.trustShell, 'space-y-12')}
          >
            <div>
              <LandingSectionHeader
                eyebrow="Trust & Privacy"
                id="privacy-title"
                title="Reflection without surrendering authority."
                titleClassName="type-landing-section"
              />
            </div>
            <div className="grid gap-6 md:grid-cols-2">
              {trustPrinciples.map((principle) => (
                <article
                  className="radius-card border-border bg-card space-y-4 border p-6"
                  key={principle.title}
                >
                  <Typography
                    as="h3"
                    className="type-landing-card-title"
                    variant="componentTitle"
                  >
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

        <section
          aria-labelledby="final-cta-title"
          className={cn(styles.finalCtaSection, 'bg-background')}
        >
          <PageShell
            as="div"
            className={cn(
              styles.exactShell,
              styles.finalCtaShell,
              'text-center',
            )}
          >
            <div className="text-measure mx-auto space-y-6">
              <Typography
                as="h2"
                className="type-landing-final"
                id="final-cta-title"
                variant="display"
              >
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
                className="type-landing-compact text-muted-foreground"
                variant="journalExcerpt"
              >
                Your first entry can be as unfinished as your thoughts.
              </Typography>
            </div>
          </PageShell>
        </section>
      </main>

      <footer
        className={cn(styles.footerSection, 'border-border bg-card border-t')}
      >
        <PageShell
          as="div"
          className={cn(styles.exactShell, styles.footerShell, 'space-y-10')}
        >
          <div className="flex flex-col gap-8 md:flex-row md:items-center md:justify-between">
            <LandingBrand />
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
            <Typography
              className="type-landing-caption text-muted-foreground"
              variant="bodySmall"
            >
              A private space for seeing how your inner world changes over time.
            </Typography>
            <Typography
              className="type-landing-caption text-muted-foreground"
              variant="bodySmall"
            >
              © 2025 Orion. All rights reserved.
            </Typography>
          </div>
        </PageShell>
      </footer>
    </div>
  );
}
