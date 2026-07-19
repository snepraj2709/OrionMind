'use client';

import { useMutation, useQuery } from '@tanstack/react-query';

import { getDataViewStatus } from '@/lib/query-state';
import type { AuthUser } from '@/services/auth';

import { profileRepository } from './mock-repository';
import type { ProfileUpdate } from './model';
import type { ProfileRepository } from './repository';

export function useProfileQuery(
  user: AuthUser | null,
  repository: ProfileRepository = profileRepository,
) {
  const query = useQuery({
    enabled: user !== null,
    queryKey: ['profile', user?.id],
    queryFn: () => {
      if (!user) throw new Error('An authenticated user is required.');
      return repository.getProfile(user);
    },
  });

  return {
    query,
    viewStatus: getDataViewStatus({
      hasData: query.data !== undefined,
      isError: query.isError,
      isFetching: query.isFetching,
      isPending: query.isPending,
    }),
  };
}

export function useUpdateProfileMutation(
  user: AuthUser | null,
  repository: ProfileRepository = profileRepository,
  onSuccess?: (
    profile: Awaited<ReturnType<ProfileRepository['updateProfile']>>,
  ) => void,
) {
  return useMutation({
    mutationFn: (update: ProfileUpdate) => {
      if (!user) throw new Error('An authenticated user is required.');
      return repository.updateProfile(user, update);
    },
    onSuccess,
  });
}
