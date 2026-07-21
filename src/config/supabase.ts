export interface SupabasePublicConfig {
  publishableKey: string;
  url: string;
}

export class SupabaseConfigurationError extends Error {
  constructor() {
    super('The public Supabase browser configuration is unavailable.');
    this.name = 'SupabaseConfigurationError';
  }
}

export function getSupabasePublicConfig(): SupabasePublicConfig {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();

  if (!url || !publishableKey) {
    throw new SupabaseConfigurationError();
  }

  return { publishableKey, url };
}
