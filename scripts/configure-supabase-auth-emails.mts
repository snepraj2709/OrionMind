import { buildAuthEmailConfig } from './supabase-auth-email-config.mts';

const projectRef =
  process.env.SUPABASE_PROJECT_REF?.trim() || 'hdpknaecnivgkadgisde';
const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL?.trim() || 'https://www.orionmind.in';
const accessToken = process.env.SUPABASE_ACCESS_TOKEN?.trim();
const config = buildAuthEmailConfig(siteUrl);

if (process.argv.includes('--dry-run')) {
  console.log(JSON.stringify(config, null, 2));
  process.exit(0);
}

if (!accessToken) {
  throw new Error(
    'SUPABASE_ACCESS_TOKEN is required. Create a Supabase Management API token with auth config write access.',
  );
}

const response = await fetch(
  `https://api.supabase.com/v1/projects/${encodeURIComponent(projectRef)}/config/auth`,
  {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(config),
  },
);

if (!response.ok) {
  throw new Error(
    `Supabase auth email configuration failed with HTTP ${response.status}.`,
  );
}

console.log(
  `Updated confirmation and recovery templates for ${projectRef} (${config.site_url}).`,
);
