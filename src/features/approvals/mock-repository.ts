import type { ApprovalStatus } from '@/features/entries';

import type { ApprovalRecord, ApprovalsQuery, ApprovalsResult } from './model';
import type { ApprovalsRepository } from './repository';

const approvalFixtures: ApprovalRecord[] = [
  {
    id: 'i1',
    content:
      'I want to establish a morning ritual centered on slow, screen-free time before engaging with the day.',
    entryDate: '2025-07-10',
    entryId: 'e1',
    kind: 'idea',
    status: 'pending_approval',
  },
  {
    id: 'i2',
    content:
      'I should practice stating my technical judgments clearly and early in meetings, rather than over-qualifying everything.',
    entryDate: '2025-07-09',
    entryId: 'e2',
    kind: 'idea',
    status: 'pending_approval',
  },
  {
    id: 'm1',
    content:
      'I found words in a work meeting that changed how I understand my own authority in technical conversations.',
    entryDate: '2025-07-09',
    entryId: 'e2',
    kind: 'memory',
    status: 'pending_approval',
  },
];

function wait(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export class MockApprovalsRepository implements ApprovalsRepository {
  private readonly approvals: ApprovalRecord[];

  constructor(
    approvals: ApprovalRecord[] = approvalFixtures,
    private readonly delay = 220,
  ) {
    this.approvals = approvals.map((item) => ({ ...item }));
  }

  async listPendingApprovals(query: ApprovalsQuery): Promise<ApprovalsResult> {
    await wait(this.delay);
    const pending = this.approvals.filter(
      (item) => item.status === 'pending_approval',
    );
    const normalizedSearch = query.search.trim().toLocaleLowerCase();
    const matching = pending
      .filter((item) => query.kind === 'all' || item.kind === query.kind)
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
    await wait(this.delay);
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
