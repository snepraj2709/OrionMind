import { describe, expect, it } from 'vitest';

import { getDataViewStatus } from './query-state';

describe('getDataViewStatus', () => {
  it.each([
    [
      { hasData: false, isError: false, isFetching: true, isPending: true },
      'loading',
    ],
    [
      { hasData: false, isError: true, isFetching: false, isPending: false },
      'initial-error',
    ],
    [
      { hasData: true, isError: true, isFetching: false, isPending: false },
      'refresh-error',
    ],
    [
      { hasData: true, isError: false, isFetching: true, isPending: false },
      'refreshing',
    ],
    [
      { hasData: true, isError: false, isFetching: false, isPending: false },
      'ready',
    ],
  ] as const)('maps query state to %s', (input, expected) => {
    expect(getDataViewStatus(input)).toBe(expected);
  });
});
