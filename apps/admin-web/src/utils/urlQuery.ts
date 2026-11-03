export function appendUrlQueryParameter(url: string, key: string, value: string): string {
  const fragmentIndex = url.indexOf('#');
  const base = fragmentIndex === -1 ? url : url.slice(0, fragmentIndex);
  const fragment = fragmentIndex === -1 ? '' : url.slice(fragmentIndex);
  const separator = base.includes('?')
    ? (base.endsWith('?') || base.endsWith('&') ? '' : '&')
    : '?';

  return `${base}${separator}${encodeURIComponent(key)}=${encodeURIComponent(value)}${fragment}`;
}
