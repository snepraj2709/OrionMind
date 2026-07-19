# Orion frontend agent rules

These rules are mandatory for every agent and contributor working on the Orion frontend.

1. Read `docs/design-system.md` before every frontend task.
2. Search existing components before creating a new component.
3. Never hardcode colors when a semantic token exists.
4. Never introduce arbitrary font sizes, spacing, or radii.
5. Never duplicate a component or helper.
6. Never directly modify shadcn primitives for feature-specific behavior.
7. Extend primitives through design-system or shared wrappers.
8. Every page must use `PageShell` or an approved layout shell.
9. Every data view must handle loading, error, empty, and success states.
10. Every interactive component must be keyboard accessible.
11. Every change must pass typecheck, lint, tests, and build.
12. When a design exception is necessary, document it in `docs/design-exceptions.md` before implementation.

## Architecture boundaries

- Use React Server Components by default. Add `"use client"` only at the smallest interactive boundary.
- Keep shadcn primitives in `src/components/ui` behavior-generic and feature-agnostic.
- Put Orion variants in `src/components/design-system` and reusable application compositions in the appropriate shared component folder.
- A feature may import another feature only through that feature's root `index.ts`; private cross-feature imports are forbidden.
- Page files compose layouts and feature APIs. They do not define reusable controls, design tokens, request clients, or mock business behavior.
- Use the typed theme and typography registries in `src/config/design-system.ts` instead of local maps.

## Required validation

Run all of the following before handoff:

```bash
npm run typecheck
npm run lint
npm test
npm run build
```

`npm run lint` includes the repository design-system policy checks. Do not bypass or weaken a check to make a feature pass; document a genuine exception first.
