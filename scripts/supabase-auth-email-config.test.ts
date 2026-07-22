import { describe, expect, it } from 'vitest';

import { buildAuthEmailConfig } from './supabase-auth-email-config.mts';

describe('Supabase auth email template contract', () => {
  it('routes confirmation and recovery token hashes through Orion', () => {
    const config = buildAuthEmailConfig('https://www.orionmind.in/');

    expect(config.site_url).toBe('https://www.orionmind.in');
    expect(config.mailer_templates_confirmation_content).toContain(
      '{{ .SiteURL }}/signup?token_hash={{ .TokenHash }}&amp;type=email',
    );
    expect(config.mailer_templates_recovery_content).toContain(
      '{{ .SiteURL }}/login?token_hash={{ .TokenHash }}&amp;type=recovery',
    );
    expect(config.mailer_templates_confirmation_content).not.toContain(
      '{{ .ConfirmationURL }}',
    );
    expect(config.mailer_templates_recovery_content).not.toContain(
      '{{ .ConfirmationURL }}',
    );
  });
});
