import type { Metadata } from 'next';
import Image from 'next/image';
import Link from 'next/link';
import {
  BookOpenText,
  Brain,
  Lightbulb,
  RefreshCw,
  Telescope,
} from 'lucide-react';

import { AppButton, Typography } from '@/components/design-system';
import { BrandMark, PageShell } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { routes } from '@/config/routes';

export const metadata: Metadata = {
  title: 'A private journal for clearer patterns',
  description:
    'Write freely, keep meaningful ideas and memories, and notice reflections and longer-term patterns with Orion.',
};

const entryOutcomes = [
  {
    label: 'Idea',
    text: 'Protect one screen-free morning each week.',
  },
  {
    label: 'Memory',
    text: 'Coffee at sunrise before the rest of the day began.',
  },
  {
    label: 'Reflection',
    text: 'Quiet beginnings restore your sense of direction.',
  },
] as const;

const features = [
  {
    title: 'Entries',
    description: 'Write or speak in your own words.',
    icon: BookOpenText,
  },
  {
    title: 'Ideas',
    description: 'Keep possibilities worth returning to.',
    icon: Lightbulb,
  },
  {
    title: 'Memories',
    description: 'Hold on to moments that reveal what matters.',
    icon: Brain,
  },
  {
    title: 'Reflections',
    description: 'Notice hidden drivers, recurring loops, and inner tensions.',
    icon: RefreshCw,
  },
  {
    title: 'Journey',
    description: 'See themes and changes emerge across time.',
    icon: Telescope,
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
              <Link href={routes.signup.path}>Create account</Link>
            </AppButton>
          </nav>
        </PageShell>
      </header>

      <main id="main-content">
        <section
          aria-labelledby="hero-title"
          className="flex min-h-svh items-center"
          data-viewport-section
        >
          <PageShell
            as="div"
            className="grid w-full items-center gap-6 lg:grid-cols-2 lg:gap-10"
          >
            <div className="text-measure space-y-4">
              <Typography className="text-primary" variant="eyebrow">
                Private journaling, clearer patterns
              </Typography>
              <Typography as="h1" id="hero-title" variant="display">
                A place for what happened—and what it may be showing you.
              </Typography>
              <Typography className="text-muted-foreground" variant="bodyLarge">
                Write freely. Orion keeps what matters close and helps you
                notice what returns over time.
              </Typography>
              <div className="flex flex-wrap items-center gap-3">
                <AppButton asChild>
                  <Link href={routes.signup.path}>Create account</Link>
                </AppButton>
                <AppButton asChild variant="secondary">
                  <Link href={routes.login.path}>Log in</Link>
                </AppButton>
              </div>
            </div>

            <aside
              aria-label="An entry becoming something to notice"
              className="border-border space-y-4 border-y py-6"
            >
              <div className="space-y-3">
                <Typography className="text-muted-foreground" variant="eyebrow">
                  From one entry
                </Typography>
                <Typography as="blockquote" variant="journalExcerpt">
                  “I keep doing my best thinking before the day begins asking
                  things of me.”
                </Typography>
              </div>
              <dl className="border-border grid grid-cols-3 gap-3 border-t pt-4">
                {entryOutcomes.map((outcome) => (
                  <div className="space-y-2" key={outcome.label}>
                    <dt className="type-metadata text-primary">
                      {outcome.label}
                    </dt>
                    <dd className="type-body-small text-muted-foreground">
                      {outcome.text}
                    </dd>
                  </div>
                ))}
              </dl>
            </aside>
          </PageShell>
        </section>

        <section
          aria-labelledby="features-title"
          className="border-border bg-sidebar flex min-h-svh items-center border-y"
          data-viewport-section
        >
          <PageShell as="div" className="w-full space-y-6 lg:space-y-10">
            <div className="text-measure space-y-3">
              <Typography className="text-primary" variant="eyebrow">
                The whole picture
              </Typography>
              <Typography as="h2" id="features-title" variant="sectionTitle">
                Five ways to stay close to what your life is teaching you.
              </Typography>
              <Typography className="text-muted-foreground" variant="body">
                Each view begins with your entries and gives you another way to
                return to what feels meaningful.
              </Typography>
            </div>

            <div className="grid grid-cols-2 gap-4 xl:grid-cols-5 xl:gap-8">
              {features.map((feature) => {
                const Icon = feature.icon;

                return (
                  <article
                    className="border-border space-y-2 border-t pt-4 last:col-span-2 xl:last:col-span-1"
                    key={feature.title}
                  >
                    <Icon aria-hidden="true" className="text-primary size-6" />
                    <div className="space-y-1">
                      <Typography as="h3" variant="componentTitle">
                        {feature.title}
                      </Typography>
                      <Typography
                        className="text-muted-foreground"
                        variant="bodySmall"
                      >
                        {feature.description}
                      </Typography>
                    </div>
                  </article>
                );
              })}
            </div>
          </PageShell>
        </section>

        <section
          aria-labelledby="product-preview-title"
          className="flex min-h-svh items-center"
          data-viewport-section
        >
          <PageShell
            as="div"
            className="grid w-full items-center gap-6 lg:grid-cols-2 lg:gap-10"
          >
            <div className="space-y-3">
              <Typography className="text-primary" variant="eyebrow">
                Inside Orion
              </Typography>
              <Typography
                as="h2"
                id="product-preview-title"
                variant="sectionTitle"
              >
                Your ideas, memories, and reflections—gathered without losing
                the original words.
              </Typography>
              <Typography className="text-muted-foreground" variant="body">
                Orion keeps each interpretation connected to the entries behind
                it, so you can decide what resonates and what does not.
              </Typography>
            </div>

            <figure className="space-y-3">
              <div className="radius-surface border-border bg-card overflow-hidden border">
                <Image
                  alt="Orion product preview showing ideas, reflections, and memories gathered from journal entries"
                  className="h-auto w-full"
                  height={941}
                  sizes="(max-width: 1440px) 93vw, 1328px"
                  src="/images/orion-product-overview.png"
                  width={1671}
                />
              </div>
              <Typography
                as="span"
                className="text-muted-foreground block"
                variant="bodySmall"
              >
                Product direction preview — ideas, memories, and reflections
                gathered in one view.
              </Typography>
            </figure>
          </PageShell>
        </section>
      </main>

      <footer
        aria-labelledby="footer-cta-title"
        className="border-border bg-secondary border-t"
      >
        <PageShell as="div" className="space-y-6 py-8">
          <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div className="text-measure space-y-2">
              <Typography
                as="h2"
                id="footer-cta-title"
                variant="componentTitle"
              >
                Begin with the entry only you can write.
              </Typography>
              <Typography className="text-muted-foreground" variant="bodySmall">
                No scoring, streaks, or performance. Just a private place to
                notice more over time.
              </Typography>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <AppButton asChild>
                <Link href={routes.signup.path}>Create account</Link>
              </AppButton>
              <AppButton asChild variant="secondary">
                <Link href={routes.login.path}>Log in</Link>
              </AppButton>
            </div>
          </div>

          <div className="border-border flex flex-col gap-4 border-t pt-4 md:flex-row md:items-center md:justify-between">
            <div className="space-y-1">
              <Typography variant="metadata">Orion</Typography>
              <Typography className="text-muted-foreground" variant="bodySmall">
                Your words first. Your interpretation always.
              </Typography>
            </div>

            <nav
              aria-label="Social media"
              className="text-muted-foreground flex items-center gap-2"
            >
              <AppButton
                aria-label="Twitter / X"
                asChild
                size="compact"
                variant="icon"
              >
                <a
                  href="https://twitter.com"
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  <svg
                    aria-hidden="true"
                    className="icon-md"
                    fill="none"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                  >
                    <path d="M5 4 19 20" />
                    <path d="M19 4 5 20" />
                  </svg>
                </a>
              </AppButton>
              <AppButton
                aria-label="LinkedIn"
                asChild
                size="compact"
                variant="icon"
              >
                <a
                  href="https://linkedin.com"
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  <svg
                    aria-hidden="true"
                    className="icon-md"
                    fill="none"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                  >
                    <rect height="18" rx="2" width="18" x="3" y="3" />
                    <path d="M8 11v5" />
                    <path d="M8 8h.01" />
                    <path d="M12 16v-5" />
                    <path d="M12 13.5a2.5 2.5 0 0 1 5 0V16" />
                  </svg>
                </a>
              </AppButton>
              <AppButton
                aria-label="Instagram"
                asChild
                size="compact"
                variant="icon"
              >
                <a
                  href="https://instagram.com"
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  <svg
                    aria-hidden="true"
                    className="icon-md"
                    fill="none"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                  >
                    <rect height="18" rx="5" width="18" x="3" y="3" />
                    <circle cx="12" cy="12" r="4" />
                    <path d="M17.5 6.5h.01" />
                  </svg>
                </a>
              </AppButton>
            </nav>
          </div>
        </PageShell>
      </footer>
    </div>
  );
}
