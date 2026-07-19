export type DataViewStatus =
  'loading' | 'initial-error' | 'refresh-error' | 'refreshing' | 'ready';

interface QueryStateInput {
  hasData: boolean;
  isError: boolean;
  isFetching: boolean;
  isPending: boolean;
}

export function getDataViewStatus({
  hasData,
  isError,
  isFetching,
  isPending,
}: QueryStateInput): DataViewStatus {
  if (isPending) return 'loading';
  if (isError) return hasData ? 'refresh-error' : 'initial-error';
  if (isFetching && hasData) return 'refreshing';
  return 'ready';
}
