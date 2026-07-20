'use client';

import { Check, X } from 'lucide-react';

import { AppButton } from '@/components/design-system';

export interface ApprovalActionsProps {
  onApprove: () => void;
  onReject: () => void;
  disabled?: boolean;
  loadingAction?: 'approve' | 'reject';
  appearance?: 'default' | 'editorial';
}

export function ApprovalActions({
  appearance = 'default',
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
        size={appearance === 'default' ? 'compact' : 'default'}
        variant={appearance === 'editorial' ? 'accentOutline' : 'primary'}
      >
        Approve
      </AppButton>
      <AppButton
        disabled={disabled || loadingAction === 'approve'}
        leftIcon={<X aria-hidden="true" />}
        loading={loadingAction === 'reject'}
        loadingLabel="Rejecting item"
        onClick={onReject}
        size={appearance === 'default' ? 'compact' : 'default'}
        variant={appearance === 'editorial' ? 'rejectOutline' : 'ghost'}
      >
        Reject
      </AppButton>
    </div>
  );
}
