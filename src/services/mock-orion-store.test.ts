import { describe, expect, it } from 'vitest';

import { MockOrionStore } from './mock-orion-store';

describe('MockOrionStore', () => {
  it('keeps entry, review queue, and saved-item state coherent', () => {
    const store = new MockOrionStore();

    expect(store.listPendingApprovals()).toHaveLength(3);
    const approved = store.decideExtractedItem({
      itemId: 'i1',
      status: 'approved',
    });

    expect(approved.status).toBe('approved');
    expect(store.listPendingApprovals()).toHaveLength(2);
    expect(store.entries[0]?.ideas[0]?.status).toBe('approved');
    expect(store.savedItems[0]).toMatchObject({
      id: 'i1',
      kind: 'idea',
    });
  });
});
