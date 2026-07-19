import { z } from 'zod';

export const profileSchema = z.object({
  displayName: z
    .string()
    .trim()
    .min(2, 'Enter at least two characters.')
    .max(80),
  email: z.email(),
  timezone: z.string().min(1, 'Choose a timezone.'),
  weekStartsOn: z.enum(['monday', 'sunday']),
});

export type Profile = z.infer<typeof profileSchema>;
export type ProfileUpdate = Pick<
  Profile,
  'displayName' | 'timezone' | 'weekStartsOn'
>;
