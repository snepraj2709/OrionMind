import type { Metadata } from 'next';

import { routes } from '@/config/routes';
import { ProfileScreen } from '@/features/profile';

export const metadata: Metadata = { title: routes.profile.label };

export default function ProfilePage() {
  return <ProfileScreen />;
}
