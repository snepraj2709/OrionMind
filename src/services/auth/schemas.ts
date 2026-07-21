import { z } from 'zod';

export const signInSchema = z.object({
  email: z.email('Enter a valid email address.'),
  password: z.string().min(1, 'Enter your password.'),
});

export const signUpSchema = signInSchema.extend({
  password: z.string().min(8, 'Password must contain at least 8 characters.'),
});

export const passwordRecoverySchema = z.object({
  email: z.email('Enter a valid email address.'),
});

export const passwordUpdateSchema = z
  .object({
    password: z.string().min(8, 'Password must contain at least 8 characters.'),
    confirmation: z.string(),
  })
  .refine((value) => value.password === value.confirmation, {
    message: 'Enter the same password twice.',
    path: ['confirmation'],
  });

export type SignInInput = z.infer<typeof signInSchema>;
export type SignUpInput = z.infer<typeof signUpSchema>;
export type PasswordRecoveryInput = z.infer<typeof passwordRecoverySchema>;
export type PasswordUpdateInput = z.infer<typeof passwordUpdateSchema>;
