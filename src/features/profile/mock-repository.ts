import type { Profile, ProfileUpdate } from './model';
import type { ProfileRepository } from './repository';
import { simulateLatency } from '@/services/mock-delay';

export class MockProfileRepository implements ProfileRepository {
  private readonly profiles = new Map<string, Profile>();

  constructor(
    private readonly seed?: Profile,
    private readonly delay = 240,
  ) {}

  async getProfile(user: { email: string; name: string }): Promise<Profile> {
    await simulateLatency(this.delay);
    const profile =
      this.profiles.get(user.email) ??
      (this.seed?.email === user.email
        ? this.seed
        : {
            displayName: user.name,
            email: user.email,
            timezone: 'Asia/Kolkata',
            weekStartsOn: 'monday' as const,
          });
    this.profiles.set(user.email, profile);
    return { ...profile };
  }

  async updateProfile(
    user: { email: string; name: string },
    update: ProfileUpdate,
  ): Promise<Profile> {
    await simulateLatency(this.delay);
    const profile =
      this.profiles.get(user.email) ?? (await this.getProfile(user));
    const updatedProfile = { ...profile, ...update };
    this.profiles.set(user.email, updatedProfile);
    return { ...updatedProfile };
  }
}

export const profileRepository = new MockProfileRepository();
