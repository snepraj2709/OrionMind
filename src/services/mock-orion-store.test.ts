import { describe, expect, it } from 'vitest';

import { MockReflectionsRepository } from '@/features/reflections';

import { MockOrionStore } from './mock-orion-store';

describe('MockOrionStore', () => {
  it('keeps entry, review queue, and saved-item state coherent', () => {
    const store = new MockOrionStore();

    expect(store.listPendingApprovals()).toHaveLength(6);
    const approved = store.decideExtractedItem({
      itemId: 'i1',
      status: 'approved',
    });

    expect(approved.status).toBe('approved');
    expect(store.listPendingApprovals()).toHaveLength(5);
    expect(store.entries[0]?.ideas[0]?.status).toBe('approved');
    expect(store.savedItems[0]).toMatchObject({
      id: 'i1',
      kind: 'idea',
    });
  });

  it('maps an approved reflection to self-knowledge evidence without saving it', () => {
    const store = new MockOrionStore();
    const savedCount = store.savedItems.length;
    const approved = store.decideExtractedItem({
      itemId: 'r1',
      status: 'approved',
    });

    expect(approved).toMatchObject({
      kind: 'reflection',
      status: 'approved',
      themes: ['personalGrowth', 'health', 'familyAndFriends'],
    });
    expect(store.savedItems).toHaveLength(savedCount);
    expect(store.listApprovedReflectionEvidence()).toEqual([
      {
        content:
          'Slow, unstructured mornings help me hear what I need before the day starts asking things of me.',
        entryDate: '2025-07-10',
      },
    ]);
  });

  it('exposes approved reflection evidence on the next Reflections load', async () => {
    const store = new MockOrionStore();
    store.decideExtractedItem({ itemId: 'r1', status: 'approved' });
    const repository = new MockReflectionsRepository([], 0, store);

    const result = await repository.getReflectionEntries('all');

    expect(result.entries).toEqual([
      {
        entry_date: '2025-07-10',
        content: {
          added_energy: [],
          drained_energy: [],
          self_knowledge: [
            'Slow, unstructured mornings help me hear what I need before the day starts asking things of me.',
          ],
        },
      },
    ]);
  });
});
