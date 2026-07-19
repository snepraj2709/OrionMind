import type { ApprovalStatus } from '@/features/entries';

import type { ApprovalRecord, ApprovalsQuery, ApprovalsResult } from './model';

export interface ApprovalsRepository {
  listPendingApprovals(query: ApprovalsQuery): Promise<ApprovalsResult>;
  decideApproval(input: {
    id: string;
    status: Exclude<ApprovalStatus, 'pending_approval'>;
  }): Promise<ApprovalRecord>;
}
