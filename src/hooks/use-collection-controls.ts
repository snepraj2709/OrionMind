'use client';

import { useState } from 'react';

import { collectionPageSize } from '@/constants/pagination';

export function useCollectionControls(initialPageSize = collectionPageSize) {
  const [search, setSearchValue] = useState('');
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSizeValue] = useState(initialPageSize);

  function setSearch(searchValue: string) {
    setSearchValue(searchValue);
    setPageIndex(0);
  }

  function setPageSize(nextPageSize: number) {
    setPageSizeValue(nextPageSize);
    setPageIndex(0);
  }

  return {
    clearSearch: () => setSearch(''),
    pageIndex,
    pageSize,
    search,
    setPageIndex,
    setPageSize,
    setSearch,
  };
}
