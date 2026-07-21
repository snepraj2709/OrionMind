import { describe, expect, it, vi } from 'vitest';

vi.mock('./fixtures', () => {
  throw new Error('Production Reflections imported test fixtures.');
});
vi.mock('./mock-repository', () => {
  throw new Error('Production Reflections imported the mock repository.');
});
vi.mock('./response-builder', () => {
  throw new Error('Production Reflections imported the test response builder.');
});

describe('Reflections production boundary', () => {
  it('does not load test-only fixtures, builders, or repositories', async () => {
    await expect(import('./index')).resolves.toBeDefined();
  });
});
