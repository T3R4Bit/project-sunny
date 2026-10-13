const BASE = '';  // Backend routes are at root level, no /api prefix

async function request(path: string, init?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
    credentials: 'include',
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  // Auth
  login: (password: string) =>
    request('/login', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  logout: () => request('/logout', { method: 'POST' }),
  status: () => request('/auth/status'),

  // Projects
  projects: () => request('/projects'),
  createProject: (data: { name: string; description?: string; tags?: string[] }) =>
    request('/projects', { method: 'POST', body: JSON.stringify(data) }),
  project: (slug: string) => request(`/projects/${slug}`),
  updateProject: (slug: string, data: Partial<{ description: string }>) =>
    request(`/projects/${slug}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteProject: (slug: string) =>
    request(`/projects/${slug}`, { method: 'DELETE' }),

  // Sessions (project-scoped)
  projectSessions: (slug: string) => request(`/projects/${slug}/sessions`),
  createProjectSession: (slug: string, data?: { title?: string }) =>
    request(`/projects/${slug}/sessions`, { method: 'POST', body: JSON.stringify(data || {}) }),
  closeProjectSession: (slug: string, sessionSlug: string, data?: { close_data?: Record<string, unknown> }) =>
    request(`/projects/${slug}/sessions/${sessionSlug}/close`, { method: 'POST', body: JSON.stringify(data || {}) }),

  // Home sessions
  homeSessions: () => request('/chats/sessions'),
  createHomeSession: (title?: string) =>
    request('/chats/sessions', { method: 'POST', body: JSON.stringify(title ? { title } : {}) }),
  closeHomeSession: (sessionSlug: string, data?: { close_data?: Record<string, unknown> }) =>
    request(`/chats/sessions/${sessionSlug}/close`, { method: 'POST', body: JSON.stringify(data || {}) }),

  // Chat
  chat: (sessionSlug: string, message: string, projectSlug?: string) =>
    request(`/chats/sessions/${sessionSlug}/chat`, {
      method: 'POST',
      body: JSON.stringify({ message, ...(projectSlug ? { project_slug: projectSlug } : {}) }),
    }),
  session: (sessionSlug: string, projectSlug?: string) =>
    request(projectSlug ? `/projects/${projectSlug}/sessions/${sessionSlug}/turns` : `/chats/sessions/${sessionSlug}`),
  streamChat: async (
    sessionSlug: string,
    message: string,
    projectSlug?: string,
    onChunk?: (text: string) => void,
    onComplete?: () => void
  ) => {
    const body: Record<string, string> = { message };
    if (projectSlug) body.project_slug = projectSlug;

    const res = await fetch(`${BASE}/chats/sessions/${sessionSlug}/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(body),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop() || '';

      for (const event of events) {
        if (!event.startsWith('data: ')) continue;
        const data = event.slice(6);
        if (data === '[DONE]') {
          onComplete?.();
          return;
        }
        const parsed = JSON.parse(data);
        if (parsed.error) throw new Error(parsed.error);
        if (parsed.text) onChunk?.(parsed.text);
      }
    }
    onComplete?.();
  },

  // Search
  search: (q: string, mode?: string) =>
    request(`/search?q=${encodeURIComponent(q)}${mode ? `&mode=${mode}` : ''}`),

  // Admin
  adminStatus: () => request('/admin/status'),
};
