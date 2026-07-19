import type { Metadata } from 'next';

import { RouteScaffold } from '@/components/shared';
import { routes } from '@/config/routes';

export const metadata: Metadata = { title: routes.entryDetail.label };

interface EntryDetailPageProps {
  params: Promise<{ entryId: string }>;
}

export default async function EntryDetailPage({
  params,
}: EntryDetailPageProps) {
  const { entryId } = await params;

  return (
    <RouteScaffold
      description="Read the journal entry and review its extracted insights."
      detail={`Entry reference: ${entryId}`}
      title={routes.entryDetail.label}
    />
  );
}
