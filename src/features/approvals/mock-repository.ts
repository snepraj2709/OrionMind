import type { ApprovalStatus } from '@/config/status';
import { mockOrionStore } from '@/services/mock-orion-store';
import { simulateLatency } from '@/services/mock-delay';

import type { ApprovalRecord, ApprovalsQuery, ApprovalsResult } from './model';
import type { ApprovalsRepository } from './repository';

export class MockApprovalsRepository implements ApprovalsRepository {
  private readonly approvals: ApprovalRecord[] | undefined;

  constructor(
    approvals?: ApprovalRecord[],
    private readonly delay = 220,
  ) {
    this.approvals = approvals?.map((item) => ({
      ...item,
      themes: [...item.themes],
    }));
  }

  async listPendingApprovals(query: ApprovalsQuery): Promise<ApprovalsResult> {
    await simulateLatency(this.delay);
    const pending = (
      this.approvals ?? mockOrionStore.listPendingApprovals()
    ).filter((item) => item.status === 'pending_approval');
    const normalizedSearch = query.search.trim().toLocaleLowerCase();
    const matching = pending
      .filter((item) => query.status === 'all' || item.status === query.status)
      .filter((item) => query.kind === 'all' || item.kind === query.kind)
      .filter(
        (item) => query.theme === 'all' || item.themes.includes(query.theme),
      )
      .filter(
        (item) =>
          normalizedSearch.length === 0 ||
          item.content.toLocaleLowerCase().includes(normalizedSearch),
      )
      .sort((left, right) => right.entryDate.localeCompare(left.entryDate));
    const start = query.pageIndex * query.pageSize;

    return {
      items: matching.slice(start, start + query.pageSize),
      total: matching.length,
      totalAll: pending.length,
    };
  }

  async decideApproval(input: {
    id: string;
    status: Exclude<ApprovalStatus, 'pending_approval'>;
  }): Promise<ApprovalRecord> {
    await simulateLatency(this.delay);

    if (!this.approvals) {
      return mockOrionStore.decideExtractedItem({
        itemId: input.id,
        status: input.status,
      });
    }

    const item = this.approvals.find((candidate) => candidate.id === input.id);
    if (!item) throw new Error('The review item was not found.');
    if (item.status !== 'pending_approval') {
      throw new Error('This item has already been reviewed.');
    }
    item.status = input.status;
    return item;
  }
}

export const approvalsRepository = new MockApprovalsRepository();
