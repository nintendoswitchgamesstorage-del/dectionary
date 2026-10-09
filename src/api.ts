export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body); } catch { /* response is not JSON */ }
    throw new Error(message);
  }
  return response.json();
}
export function post<T>(path: string, body: unknown): Promise<T> {
  return api<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
}
export async function exportProject(format: string, project: unknown) {
  const response = await fetch('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ format, project }) });
  if (!response.ok) throw new Error('The export could not be created. Please try again.');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url; link.download = `lexical-alchemy.${format === 'markdown' ? 'md' : format}`; link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
