import { Typography } from '@/components/design-system';
import { PageHeader, PageShell, Section } from '@/components/layout';

export interface RouteScaffoldProps {
  title: string;
  description: string;
  detail?: string;
}

export function RouteScaffold({
  description,
  detail = 'The route and application shell are ready. Feature content will be implemented in its dedicated slice.',
  title,
}: RouteScaffoldProps) {
  return (
    <PageShell className="space-y-8">
      <PageHeader description={description} title={title} />
      <Section title="Route ready">
        <Typography
          className="text-muted-foreground text-measure"
          variant="body"
        >
          {detail}
        </Typography>
      </Section>
    </PageShell>
  );
}
