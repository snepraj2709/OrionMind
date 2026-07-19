import type { Metadata } from 'next';

import { routes } from '@/config/routes';
import { ApprovalsScreen } from '@/features/approvals';

export const metadata: Metadata = { title: routes.approvals.label };

export default function ApprovalsPage() {
  return <ApprovalsScreen />;
}
