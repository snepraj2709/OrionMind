import type { Profile, ProfileUpdate } from './model';
import type { ProfileRepository } from './repository';

const defaultProfile: Profile = {
  displayName: 'Maya Chen',
  email: 'maya@example.com',
  timezone: 'Asia/Kolkata',
  weekStartsOn: 'monday',
};

function wait(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export class MockProfileRepository implements ProfileRepository {
  private profile: Profile;

  constructor(
    profile: Profile = defaultProfile,
    private readonly delay = 240,
  ) {
    this.profile = { ...profile };
  }

  async getProfile(): Promise<Profile> {
    await wait(this.delay);
    return { ...this.profile };
  }

  async updateProfile(update: ProfileUpdate): Promise<Profile> {
    await wait(this.delay);
    this.profile = { ...this.profile, ...update };
    return { ...this.profile };
  }
}

export const profileRepository = new MockProfileRepository();
