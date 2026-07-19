import { expect, test } from '@playwright/test';

import { routes } from '../src/config/routes';
import { logIn } from './helpers/auth';

test.describe.configure({ mode: 'serial' });

const reflectionViews = [
  { label: 'Hidden drivers', slug: 'hidden-drivers' },
  { label: 'Recurring loops', slug: 'recurring-loops' },
  { label: 'Inner tensions', slug: 'inner-tensions' },
] as const;

test('matches all Reflections tabs at desktop width', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await logIn(page);
  await page.goto(routes.reflections.path);

  await expect(
    page.getByRole('heading', { level: 1, name: routes.reflections.label }),
  ).toBeVisible();
  await expect(
    page.getByText('Patterns taking shape across 8 entries from 14 Apr–8 May.'),
  ).toBeVisible();

  for (const view of reflectionViews) {
    await page.getByRole('radio', { name: view.label }).click();
    const panel = page.getByRole('region', {
      name: `${view.label} reflection`,
    });
    await expect(panel).toBeVisible();

    const panelBox = await panel.boundingBox();
    expect(panelBox?.height).toBeLessThanOrEqual(1000);

    await expect(page).toHaveScreenshot(
      `reflections-${view.slug}-desktop.png`,
      { fullPage: true },
    );
  }
});

test('matches all Reflections tabs without mobile page overflow', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await logIn(page);
  await page.goto(routes.reflections.path);

  await expect(
    page.getByText('Patterns taking shape across 8 entries from 14 Apr–8 May.'),
  ).toBeVisible();

  for (const view of reflectionViews) {
    await page.getByRole('radio', { name: view.label }).click();
    await expect(
      page.getByRole('region', { name: `${view.label} reflection` }),
    ).toBeVisible();

    const dimensions = await page.evaluate(() => ({
      content: document.documentElement.scrollWidth,
      viewport: document.documentElement.clientWidth,
    }));
    expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);

    await expect(page).toHaveScreenshot(`reflections-${view.slug}-mobile.png`, {
      fullPage: true,
    });
  }
});

test('reveals contextual evidence and records rejected insight feedback', async ({
  page,
}) => {
  await logIn(page);
  await page.goto(routes.reflections.path);

  const originalSentence =
    'Explaining a difficult idea to someone else made the whole subject click for me.';
  await expect(page.getByText(originalSentence)).toHaveCount(0);
  await page.getByRole('button', { name: 'Why am I seeing this?' }).click();
  await expect(
    page.getByRole('heading', { name: 'Supporting entries' }),
  ).toBeVisible();
  await expect(page.getByText(originalSentence)).toBeVisible();
  await page.getByRole('button', { name: 'Close' }).click();

  await page.getByRole('button', { name: 'Not true for me' }).click();
  await expect(
    page.getByText(/will not treat this as an accepted self-pattern/),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Not true for me' }),
  ).toHaveAttribute('aria-pressed', 'true');
});
