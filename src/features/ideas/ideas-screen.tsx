import { SavedItemsScreen } from '@/components/shared';

export function IdeasScreen() {
  return (
    <SavedItemsScreen
      description="Ideas you chose to carry forward from your journal."
      emptyDescription="Approve an idea in Review and it will become part of this collection."
      emptyTitle="No saved ideas yet"
      kind="idea"
      title="Ideas"
    />
  );
}
