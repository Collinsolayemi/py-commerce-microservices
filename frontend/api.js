export class ApiError extends Error {
  constructor(message, status = 0) { super(message); this.status = status; }
}
export function errorMessage(detail, fallback) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(error => `${(error.loc || []).filter(part => part !== 'body').join(' ')}: ${error.msg || 'Invalid value'}`).join('. ');
  return fallback;
}
export async function request(path, { token, method = 'GET', body, signal } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  try {
    const response = await fetch(`/api${path}`, {
      method, headers: { 'Accept': 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body ? JSON.stringify(body) : undefined, signal: controller.signal,
    });
    const text = await response.text();
    let data;
    try { data = text ? JSON.parse(text) : null; } catch { throw new ApiError('The service returned an unexpected response.', response.status); }
    if (!response.ok) throw new ApiError(errorMessage(data?.detail, `Request failed (${response.status}). Please try again.`), response.status);
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(error.name === 'AbortError' ? 'The request timed out. Check your orders before retrying a checkout.' : 'We couldn’t reach the service. Please check your connection and try again.');
  } finally { clearTimeout(timeout); signal?.removeEventListener('abort', abort); }
}
