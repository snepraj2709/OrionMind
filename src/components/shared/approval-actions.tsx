'use client';

import { Check, X } from 'lucide-react';

import { AppButton } from '@/components/design-system';

export interface ApprovalActionsProps {
  onApprove: () => void;
  onReject: () => void;
  disabled?: boolean;
  loadingAction?: 'approve' | 'reject';
}

export function ApprovalActions({
  disabled = false,
  loadingAction,
  onApprove,
  onReject,
}: ApprovalActionsProps) {
  return (
    <div className="flex flex-wrap gap-3" role="group" aria-label="Review item">
      <AppButton
        disabled={disabled || loadingAction === 'reject'}
        leftIcon={<Check aria-hidden="true" />}
        loading={loadingAction === 'approve'}
        loadingLabel="Approving item"
        onClick={onApprove}
        size="compact"
      >
        Approve
      </AppButton>
      <AppButton
        disabled={disabled || loadingAction === 'approve'}
        leftIcon={<X aria-hidden="true" />}
        loading={loadingAction === 'reject'}
        loadingLabel="Rejecting item"
        onClick={onReject}
        size="compact"
        variant="ghost"
      >
        Reject
      </AppButton>
    </div>
  );
}
