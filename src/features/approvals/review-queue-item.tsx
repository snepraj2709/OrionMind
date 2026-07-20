import { Typography } from '@/components/design-system';
import { ApprovalActions } from '@/components/shared';

export interface ReviewQueueItemProps {
  content: string;
  disabled?: boolean;
  loadingAction?: 'approve' | 'reject';
  onApprove: () => void;
  onReject: () => void;
}

export function ReviewQueueItem({
  content,
  disabled = false,
  loadingAction,
  onApprove,
  onReject,
}: ReviewQueueItemProps) {
  return (
    <li>
      <article className="space-y-4 py-6">
        <Typography className="text-measure-wide" variant="journalExcerpt">
          {content}
        </Typography>
        <ApprovalActions
          appearance="editorial"
          disabled={disabled}
          loadingAction={loadingAction}
          onApprove={onApprove}
          onReject={onReject}
        />
      </article>
      <hr className="border-border" />
    </li>
  );
}
