'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Controller, useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { Surface } from '@/components/cards';
import { AppButton, Typography } from '@/components/design-system';
import { PageErrorState, SkeletonList } from '@/components/feedback';
import {
  FormError,
  FormField,
  SelectField,
  SubmitButton,
  TextInput,
} from '@/components/forms';
import { PageHeader, PageShell, Section } from '@/components/layout';
import { routes } from '@/config/routes';
import { SignOutButton, useAuth } from '@/features/auth';
import { useOnlineStatus } from '@/hooks';

import { profileRepository } from './mock-repository';
import { profileSchema, type Profile, type ProfileUpdate } from './model';
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
  const { user } = useAuth();
  const isOnline = useOnlineStatus();
  const profileQuery = useQuery({
    queryKey: ['profile', user?.id],
    queryFn: () => repository.getProfile(),
  });
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
  const updateMutation = useMutation({
    mutationFn: (update: ProfileUpdate) => repository.updateProfile(update),
    onSuccess: (profile) => {
      form.reset(profile);
      toast.success('Profile saved');
    },
  });

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
        description="Manage how Orion addresses you and presents dates across your journal."
        title={routes.profile.label}
      />

      {profileQuery.isPending ? <SkeletonList count={3} /> : null}
      {profileQuery.isError ? (
        <PageErrorState
          action={
            <AppButton
              onClick={() => void profileQuery.refetch()}
              variant="secondary"
            >
              Retry
            </AppButton>
          }
          description="Orion could not load your profile settings."
          title="Profile settings are unavailable"
        />
      ) : null}

      {profileQuery.data ? (
        <form
          className="space-y-12"
          noValidate
          onSubmit={form.handleSubmit(handleSubmit)}
        >
          <Section
            description="This information identifies your account and personalizes your experience."
            headingId="profile-details-heading"
            title="Profile details"
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
              <FormField
                description="Your email is managed by your authentication provider."
                id="email"
                label="Email"
              >
                <TextInput
                  disabled
                  readOnly
                  type="email"
                  {...form.register('email')}
                />
              </FormField>
            </Surface>
          </Section>

          <Section
            description="These settings control how dates and weekly summaries are organized."
            headingId="journal-preferences-heading"
            title="Journal preferences"
          >
            <Surface className="grid gap-6 p-6 md:grid-cols-2">
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
              <Controller
                control={form.control}
                name="weekStartsOn"
                render={({ field }) => (
                  <SelectField
                    id="week-start"
                    label="Week starts on"
                    onValueChange={field.onChange}
                    options={[
                      { label: 'Monday', value: 'monday' },
                      { label: 'Sunday', value: 'sunday' },
                    ]}
                    value={field.value}
                  />
                )}
              />
            </Surface>
          </Section>

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

      <Section
        description="End your current Orion session on this device."
        headingId="session-heading"
        title="Session"
      >
        <Surface className="items-start gap-4 p-6">
          <Typography variant="body">
            Signed in as {user?.email ?? 'your account'}.
          </Typography>
          <SignOutButton />
        </Surface>
      </Section>
    </PageShell>
  );
}
