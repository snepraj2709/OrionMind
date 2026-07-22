# Supabase authentication email templates

Orion verifies signup and recovery emails on its own authenticated routes using
Supabase `token_hash` values. This avoids coupling email links to a browser-local
PKCE verifier and keeps callback behavior consistent across tabs and devices.

## Production contract

- Site URL: `https://www.orionmind.in`
- Confirm signup callback:
  `https://www.orionmind.in/signup?token_hash=...&type=email`
- Password recovery callback:
  `https://www.orionmind.in/login?token_hash=...&type=recovery`
- Successful confirmation clears the temporary session and routes to
  `/login?state=email_confirmed`.
- Successful recovery opens Orion's **Set a new password** screen with **New
  password** and **Confirm new password** fields.

## Apply through the Management API

Create a Supabase Management API token with auth configuration write access,
then run:

```bash
SUPABASE_ACCESS_TOKEN='your-management-token' \
SUPABASE_PROJECT_REF='hdpknaecnivgkadgisde' \
NEXT_PUBLIC_SITE_URL='https://www.orionmind.in' \
npm run auth:configure-emails
```

Inspect the exact payload without changing Supabase:

```bash
npm run auth:configure-emails -- --dry-run
```

## Dashboard fallback

In **Authentication → Email Templates → Confirm signup**, use:

```html
<h2>Confirm your email address</h2>
<p>Confirm this email address to finish creating your Orion account.</p>
<p>
  <a href="{{ .SiteURL }}/signup?token_hash={{ .TokenHash }}&amp;type=email"
    >Confirm email address</a
  >
</p>
<p>This link expires shortly and can only be used once.</p>
```

In **Authentication → Email Templates → Reset password**, use:

```html
<h2>Reset your password</h2>
<p>Follow the link below to choose a new Orion password.</p>
<p>
  <a href="{{ .SiteURL }}/login?token_hash={{ .TokenHash }}&amp;type=recovery"
    >Reset password</a
  >
</p>
<p>If you did not request this, you can safely ignore this email.</p>
```

Do not replace these links with `{{ .ConfirmationURL }}`. Orion's callback
routes own the verification step and immediately remove the token hash from the
browser URL after Supabase consumes it.
