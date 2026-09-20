// Local date and time as plain ASCII, for example "2026-09-20 14:05". Locale
// formatting is avoided because some locales insert characters outside ASCII.

export function formatLocal(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const two = (value: number): string => String(value).padStart(2, "0");
  const day = `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())}`;
  return `${day} ${two(date.getHours())}:${two(date.getMinutes())}`;
}
