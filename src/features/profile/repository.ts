import type { Profile, ProfileUpdate } from './model';

export interface ProfileRepository {
  getProfile(): Promise<Profile>;
  updateProfile(update: ProfileUpdate): Promise<Profile>;
}
