# Checkpoint 01 — Frontend foundation

Date: 2026-07-19

## Outcome

The Orion frontend foundation is implemented as a strict TypeScript Next.js App Router project. It includes the requested tooling, folder boundaries, providers, semantic design tokens, error-handling foundation, and automated test/build configuration.

No visual feature pages were implemented. The only application route is the non-visual `GET /api/health` endpoint; Next.js also emits its framework not-found boundary.

## Implemented foundation

- Next.js App Router with React Server Components as the default.
- Strict TypeScript and requested `@/…` import aliases.
- Tailwind CSS v4 through `@tailwindcss/postcss`.
- Light-only Orion semantic tokens and Tailwind theme mappings.
- shadcn/ui CLI configuration with React Server Component support, CSS variables, Lucide icons, and the `new-york` style.
- Root metadata and Inter/Lora loading through `next/font`.
- Root client-provider boundary containing TanStack Query and Sonner.
- Shared `AppError` type, safe unknown-error normalization, route error boundary, global error boundary, not-found boundary, and loading announcement.
- Vitest, React Testing Library, Playwright, ESLint, Prettier, Husky, and lint-staged configuration.
- Requested component, feature, service, configuration, hook, style, and type directories.

## Installed architecture dependencies

Key resolved versions from `package-lock.json` and the installed dependency tree:

| Package                       | Version |
| ----------------------------- | ------: |
| Next.js                       | 16.2.10 |
| React / React DOM             |  19.2.7 |
| TypeScript                    |   6.0.3 |
| Tailwind CSS / PostCSS plugin |   4.3.3 |
| TanStack Query                | 5.101.2 |
| TanStack Table                |  8.21.3 |
| React Hook Form               |  7.82.0 |
| Zod                           |   4.4.3 |
| Lucide React                  |  1.25.0 |
| Sonner                        |   2.0.7 |
| Vitest                        |  4.1.10 |
| Playwright Test               |  1.61.1 |
| ESLint                        |  9.39.5 |
| Prettier                      |   3.9.5 |

No shadcn component catalog was bulk-installed. The project contains only the shadcn configuration and dependencies approved by the architecture; individual primitives can be added when a feature requires them.

## Source structure

```text
src/
├── app/
│   ├── (public)/
│   ├── (auth)/
│   ├── (protected)/
│   ├── api/health/route.ts
│   ├── layout.tsx
│   ├── error.tsx
│   ├── global-error.tsx
│   ├── loading.tsx
│   ├── not-found.tsx
│   └── globals.css
├── components/
│   ├── ui/
│   ├── design-system/
│   ├── shared/
│   ├── layout/
│   ├── feedback/
│   └── data-display/
├── features/
│   ├── auth/
│   ├── entries/
│   ├── approvals/
│   ├── ideas/
│   ├── memories/
│   ├── reflections/
│   ├── journey/
│   └── profile/
├── config/
├── constants/
├── hooks/
├── lib/
├── providers/
├── services/
├── styles/
├── test/
└── types/
```

Empty architectural boundaries contain an index module or `.gitkeep` so the structure is retained without introducing placeholder page implementations.

## Import aliases

The root `@/*` alias and explicit aliases are configured in `tsconfig.json`:

- `@/components/*`
- `@/features/*`
- `@/lib/*`
- `@/services/*`
- `@/types/*`

Vitest resolves the same `@` source root.

## Client boundaries

`"use client"` is limited to:

- TanStack Query and root provider composition.
- Route/global error retry boundaries.
- The shared interactive error fallback.

The root layout, metadata, loading boundary, not-found boundary, and health route remain server-side.

## Validation evidence

All requested commands pass on Node.js 22.23.1 and npm 10.9.8:

| Command                | Result                                                 |
| ---------------------- | ------------------------------------------------------ |
| `npm run typecheck`    | Passed — TypeScript emitted no errors.                 |
| `npm run lint`         | Passed — ESLint emitted no warnings or errors.         |
| `npm test`             | Passed — 1 test file, 2 tests.                         |
| `npm run build`        | Passed — Next.js 16.2.10 production build completed.   |
| `npm run format:check` | Passed — all included files match Prettier formatting. |

Production build routes:

```text
○ /_not-found
ƒ /api/health
```

## Decisions and limitations

- The current source-backed font decision is Inter plus Lora. The older Crimson Pro reference remains an open design question and can be changed centrally before visual page work.
- The architecture documents remain unchanged by this checkpoint.
- `npm install` reported two moderate-severity advisories. A live `npm audit` request was not permitted because it would send the project's dependency graph to an external service without explicit authorization. `npm audit --offline` reported zero cached advisories, but that is not equivalent to a current online audit.
- Playwright is configured, but no browser binaries or route tests were added because visual routes are intentionally outside this checkpoint.

## Next checkpoint

Resolve the documented navigation/font/sidebar decisions, then implement the design-system primitives and shared application shell before starting feature pages.
