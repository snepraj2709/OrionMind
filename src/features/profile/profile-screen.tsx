'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { Surface } from '@/components/cards';
import { Typography } from '@/components/design-system';
import { DataViewStatus } from '@/components/feedback';
import {
  FormError,
  FormField,
  SelectField,
  SubmitButton,
  TextInput,
} from '@/components/forms';
import { PageHeader, PageShell } from '@/components/layout';
import { routes } from '@/config/routes';
import { dataViewMessages } from '@/config/messages';
import { SignOutButton, useAuth } from '@/features/auth';
import { useOnlineStatus } from '@/hooks';

import { profileRepository } from './mock-repository';
import { profileSchema, type Profile } from './model';
import { useProfileQuery, useUpdateProfileMutation } from './queries';
import type { ProfileRepository } from './repository';

const timezoneOptions = [
  { label: 'India Standard Time', value: 'Asia/Kolkata' },
  { label: 'Pacific Time', value: 'America/Los_Angeles' },
  { label: 'Eastern Time', value: 'America/New_York' },
  { label: 'Greenwich Mean Time', value: 'Europe/London' },
  { label: 'Central European Time', value: 'Europe/Paris' },
  { label: 'Japan Standard Time', value: 'Asia/Tokyo' },
];

export interface ProfileScreenProps {
  repository?: ProfileRepository;
}

export function ProfileScreen({
  repository = profileRepository,
}: ProfileScreenProps) {
  const { updateUser, user } = useAuth();
  const isOnline = useOnlineStatus();
  const { query: profileQuery, viewStatus } = useProfileQuery(user, repository);
  const form = useForm<Profile>({
    resolver: zodResolver(profileSchema),
    values: profileQuery.data,
    defaultValues: {
      displayName: '',
      email: user?.email ?? '',
      timezone: 'Asia/Kolkata',
      weekStartsOn: 'monday',
    },
  });
  const updateMutation = useUpdateProfileMutation(
    user,
    repository,
    (profile) => {
      form.reset(profile);
      updateUser({ name: profile.displayName });
      toast.success('Profile saved');
    },
  );

  function handleSubmit(values: Profile) {
    if (!isOnline) return;
    updateMutation.mutate({
      displayName: values.displayName,
      timezone: values.timezone,
      weekStartsOn: values.weekStartsOn,
    });
  }

  return (
    <PageShell className="space-y-12">
      <PageHeader
        description="Manage your account and privacy settings."
        title={routes.profile.label}
      />

      <DataViewStatus
        initialError={dataViewMessages.profile.initial}
        onRetry={() => void profileQuery.refetch()}
        refreshError={dataViewMessages.profile.refresh}
        refreshingLabel="Refreshing profile settings…"
        status={viewStatus}
      />

      {profileQuery.data ? (
        <form
          className="space-y-12"
          noValidate
          onSubmit={form.handleSubmit(handleSubmit)}
        >
          <Surface className="grid gap-6 p-6 md:grid-cols-2">
            <FormField
              error={form.formState.errors.displayName?.message}
              id="display-name"
              label="Display name"
              required
            >
              <TextInput
                autoComplete="name"
                {...form.register('displayName')}
              />
            </FormField>
            <FormField id="email" label="Email">
              <TextInput
                disabled
                readOnly
                type="email"
                {...form.register('email')}
              />
            </FormField>
            <Controller
              control={form.control}
              name="timezone"
              render={({ field, fieldState }) => (
                <SelectField
                  error={fieldState.error?.message}
                  id="timezone"
                  label="Timezone"
                  onValueChange={field.onChange}
                  options={timezoneOptions}
                  required
                  value={field.value}
                />
              )}
            />
          </Surface>

          {!isOnline ? (
            <FormError>
              You are offline. Reconnect before saving profile changes.
            </FormError>
          ) : null}
          {updateMutation.isError ? (
            <FormError>
              Orion could not save these changes. Try again.
            </FormError>
          ) : null}

          <div className="border-border bg-background flex flex-col gap-3 border-t py-4 sm:flex-row sm:items-center sm:justify-between">
            <Typography
              aria-live="polite"
              className="text-muted-foreground"
              variant="metadata"
            >
              {form.formState.isDirty
                ? 'You have unsaved changes.'
                : 'All changes are saved.'}
            </Typography>
            <SubmitButton
              disabled={!form.formState.isDirty || !isOnline}
              loading={updateMutation.isPending}
              loadingLabel="Saving profile"
            >
              Save changes
            </SubmitButton>
          </div>
        </form>
      ) : null}

      <Surface className="flex-row items-center justify-between gap-4 p-6">
        <Typography variant="body">
          Signed in as {user?.email ?? 'your account'}.
        </Typography>
        <SignOutButton />
      </Surface>
    </PageShell>
  );
}
