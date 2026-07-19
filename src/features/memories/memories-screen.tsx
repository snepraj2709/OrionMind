import { SavedItemsScreen } from '@/components/shared';
import { routes } from '@/config/routes';

export function MemoriesScreen() {
  return (
    <SavedItemsScreen
      description="Moments and realizations you chose to keep close."
      emptyDescription="Approve a memory in Review and it will become part of this collection."
      emptyTitle="No saved memories yet"
      kind="memory"
      title={routes.memories.label}
    />
  );
}
