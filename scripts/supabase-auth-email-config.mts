export interface SupabaseAuthEmailConfig {
  site_url: string;
  mailer_subjects_confirmation: string;
  mailer_subjects_recovery: string;
  mailer_templates_confirmation_content: string;
  mailer_templates_recovery_content: string;
}

function normalizeSiteUrl(siteUrl: string) {
  const parsed = new URL(siteUrl);
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    throw new Error('The Supabase site URL must use HTTP or HTTPS.');
  }
  return parsed.origin;
}

export function buildAuthEmailConfig(
  siteUrl: string,
): SupabaseAuthEmailConfig {
  return {
    site_url: normalizeSiteUrl(siteUrl),
    mailer_subjects_confirmation: 'Confirm your Orion email address',
    mailer_subjects_recovery: 'Reset your Orion password',
    mailer_templates_confirmation_content:
      '<h2>Confirm your email address</h2><p>Confirm this email address to finish creating your Orion account.</p><p><a href="{{ .SiteURL }}/signup?token_hash={{ .TokenHash }}&amp;type=email">Confirm email address</a></p><p>This link expires shortly and can only be used once.</p>',
    mailer_templates_recovery_content:
      '<h2>Reset your password</h2><p>Follow the link below to choose a new Orion password.</p><p><a href="{{ .SiteURL }}/login?token_hash={{ .TokenHash }}&amp;type=recovery">Reset password</a></p><p>If you did not request this, you can safely ignore this email.</p>',
  };
}
