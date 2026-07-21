import type { Metadata } from 'next';
import { routes } from '@/config/routes';
import { SignupScreen } from '@/features/auth';

export const metadata: Metadata = { title: routes.signup.label };

export default function SignupPage() {
  return <SignupScreen />;
}
