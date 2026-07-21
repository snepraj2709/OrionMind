import { Typography } from '@/components/design-system';
import { AuthShell, BrandMark } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { routes } from '@/config/routes';

export function AuthConfigurationNotice() {
  return (
    <AuthShell
      brand={<BrandMark />}
      description="Authentication needs the public Supabase browser configuration."
      footer={
        <AppLink className="type-metadata" href={routes.home.path}>
          Return home
        </AppLink>
      }
      title="Supabase setup required"
    >
      <Typography
        className="text-muted-foreground"
        role="status"
        variant="body"
      >
        Add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY to
        the root environment file, restart Next.js, and reload. Only public
        browser credentials belong here.
      </Typography>
    </AuthShell>
  );
}
