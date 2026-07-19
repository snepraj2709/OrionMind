const longDateFormatter = new Intl.DateTimeFormat('en', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  timeZone: 'UTC',
});

export function formatLongDate(date: string) {
  return longDateFormatter.format(new Date(date));
}
