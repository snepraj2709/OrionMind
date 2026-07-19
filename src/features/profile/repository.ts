import type { Profile, ProfileUpdate } from './model';

export interface ProfileRepository {
  getProfile(user: { email: string; name: string }): Promise<Profile>;
  updateProfile(
    user: { email: string; name: string },
    update: ProfileUpdate,
  ): Promise<Profile>;
}
