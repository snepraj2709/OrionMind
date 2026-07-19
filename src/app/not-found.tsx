export default function NotFound() {
  return (
    <main className="page-shell" id="main-content">
      <div className="max-w-text space-y-2">
        <h1 className="text-page-title">Page not found</h1>
        <p className="text-muted-foreground">
          The requested Orion page does not exist.
        </p>
      </div>
    </main>
  );
}
