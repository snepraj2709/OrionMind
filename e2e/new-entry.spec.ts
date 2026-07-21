import { expect, test } from '@playwright/test';

import { routes } from '../src/config/routes';
import { logIn } from './helpers/auth';

const createdEntry = {
  id: '8a7cc7df-94e5-41b4-b983-ab6ddda47785',
  content: 'Created entry',
  input_type: 'text',
  entry_date: '2026-07-21',
  original_theme_config_id: '046870f3-a50f-4406-a9d8-36e774a793f1',
  processing_status: 'pending',
  processing_error_code: null,
  created_at: '2026-07-21T10:00:00Z',
  classification: null,
  ideas: [],
  extracted_memories: [],
  reflections: [],
};

async function interceptComposerBackend(page: import('@playwright/test').Page) {
  await page.route('**/api/v1/entry/draft', async (route) => {
    const method = route.request().method();
    const content =
      method === 'PUT'
        ? (route.request().postDataJSON() as { content: string }).content
        : null;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        content: method === 'DELETE' ? null : content,
        updated_at: content ? '2026-07-21T10:00:00Z' : null,
      }),
    });
  });
}

test('matches the blank text composer at desktop width', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await interceptComposerBackend(page);
  await logIn(page);
  await page.goto(routes.newEntry.path);

  await expect(
    page.getByRole('heading', { level: 1, name: routes.newEntry.label }),
  ).toBeVisible();
  await expect(page.getByLabel('Your entry')).toBeEmpty();

  await expect(page).toHaveScreenshot('new-entry-text-desktop.png', {
    fullPage: true,
  });
});

test('matches voice capture without mobile page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await interceptComposerBackend(page);
  await logIn(page);
  await page.goto(routes.newEntry.path);
  await page.getByRole('radio', { name: 'Record' }).click();

  await expect(
    page.getByText(/transcription and processesing begin when you finish/i),
  ).toBeVisible();
  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);

  await expect(page).toHaveScreenshot('new-entry-voice-mobile.png', {
    fullPage: true,
  });
});

test('keeps unsaved text when navigation is cancelled', async ({ page }) => {
  await interceptComposerBackend(page);
  await logIn(page);
  await page.goto(routes.newEntry.path);
  await page
    .getByLabel('Your entry')
    .fill('A thought that should not disappear accidentally.');

  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toBe(
      'Leave this entry? Your unsaved changes will be lost.',
    );
    await dialog.dismiss();
  });
  await page
    .getByRole('navigation', { name: 'breadcrumb' })
    .getByRole('link', { name: routes.entries.label })
    .click();

  await expect(page).toHaveURL(routes.newEntry.path);
  await expect(page.getByLabel('Your entry')).toHaveValue(
    'A thought that should not disappear accidentally.',
  );
});

test('sends the real text and voice request shapes without live writes', async ({
  page,
}) => {
  const calls: Array<{
    body?: unknown;
    contentType?: string;
    idempotencyKey?: string;
    method: string;
    path: string;
    rawBody?: string;
  }> = [];
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }),
      },
    });
    class BrowserTestMediaRecorder {
      mimeType = 'audio/webm;codecs=opus';
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onstop: ((event: Event) => void) | null = null;
      state: RecordingState = 'inactive';
      constructor() {}
      start() {
        this.state = 'recording';
      }
      pause() {
        this.state = 'paused';
      }
      resume() {
        this.state = 'recording';
      }
      stop() {
        this.state = 'inactive';
        this.ondataavailable?.({
          data: new Blob(['voice'], { type: this.mimeType }),
        });
        this.onstop?.(new Event('stop'));
      }
    }
    Object.defineProperty(window, 'MediaRecorder', {
      configurable: true,
      value: BrowserTestMediaRecorder,
    });
  });
  await interceptComposerBackend(page);
  await page.route('**/api/v1/entry', async (route) => {
    const request = route.request();
    calls.push({
      body: request.postDataJSON(),
      idempotencyKey: request.headers()['idempotency-key'],
      method: request.method(),
      path: new URL(request.url()).pathname,
    });
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify(createdEntry),
    });
  });
  await page.route('**/api/v1/entries/voice', async (route) => {
    const request = route.request();
    calls.push({
      contentType: request.headers()['content-type'],
      idempotencyKey: request.headers()['idempotency-key'],
      method: request.method(),
      path: new URL(request.url()).pathname,
      rawBody: request.postDataBuffer()?.toString('utf8'),
    });
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({ ...createdEntry, input_type: 'audio' }),
    });
  });
  await page.route('**/api/v1/entries?*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 10 }),
    }),
  );

  await logIn(page);
  await page.goto(routes.newEntry.path);
  await page.getByLabel('Your entry').fill('  Browser contract text  ');
  await page.getByRole('button', { name: 'Add' }).click();
  await expect(page).toHaveURL(routes.entries.path);

  await page.goto(routes.newEntry.path);
  await page.getByRole('radio', { name: 'Record' }).click();
  await page.getByRole('button', { name: 'Start' }).click();
  await page.getByRole('button', { name: 'Stop' }).click();
  await page.getByRole('button', { name: 'Add' }).click();
  await expect(page).toHaveURL(routes.entries.path);

  expect(calls[0]).toMatchObject({
    body: { content: 'Browser contract text' },
    idempotencyKey: undefined,
    method: 'POST',
    path: '/api/v1/entry',
  });
  expect(calls[1]).toMatchObject({
    method: 'POST',
    path: '/api/v1/entries/voice',
  });
  expect(calls[1]?.idempotencyKey).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
  );
  expect(calls[1]?.contentType).toMatch(/^multipart\/form-data; boundary=/);
  expect(calls[1]?.rawBody).toContain('name="audio"');
  expect(calls[1]?.rawBody).toContain('Content-Type: audio/webm');
});
