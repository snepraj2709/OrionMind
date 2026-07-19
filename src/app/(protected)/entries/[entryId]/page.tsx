import type { Metadata } from 'next';

import { routes } from '@/config/routes';
import { EntryDetailScreen } from '@/features/entries';

export const metadata: Metadata = { title: routes.entryDetail.label };

interface EntryDetailPageProps {
  params: Promise<{ entryId: string }>;
}

export default async function EntryDetailPage({
  params,
}: EntryDetailPageProps) {
  const { entryId } = await params;

  return <EntryDetailScreen entryId={entryId} />;
}
