import { Typography } from '@/components/design-system';
import { PageShell } from '@/components/layout';

export default function NotFound() {
  return (
    <PageShell as="main" id="main-content">
      <div className="text-measure space-y-2">
        <Typography as="h1" variant="pageTitle">
          Page not found
        </Typography>
        <Typography className="text-muted-foreground" variant="body">
          The requested Orion page does not exist.
        </Typography>
      </div>
    </PageShell>
  );
}
