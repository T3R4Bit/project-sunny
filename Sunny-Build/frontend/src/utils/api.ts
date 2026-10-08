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
  login: (username: string, password: string) =>
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
    request(`/projects/${slug}`, { method: 'POST', body: JSON.stringify(data) }),
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
  createHomeSession: () => request('/chats/sessions', { method: 'POST', body: JSON.stringify({}) }),
  closeHomeSession: (sessionSlug: string, data?: { close_data?: Record<string, unknown> }) =>
    request(`/chats/sessions/${sessionSlug}/close`, { method: 'POST', body: JSON.stringify(data || {}) }),

  // Chat
  chat: (sessionSlug: string, message: string, projectSlug?: string) =>
    request(`/chats/sessions/${sessionSlug}/chat`, {
      method: 'POST',
      body: JSON.stringify({ message, ...(projectSlug ? { project_slug: projectSlug } : {}) }),
    }),
  streamChat: async (
    sessionSlug: string,
    message: string,
    projectSlug?: string,
    onChunk?: (text: string) => void,
    onComplete?: () => void
  ) => {
    const body: Record<string, string> = { message };
    if (projectSlug) body.project_slug = projectSlug;

    const res = await fetch(`/api/chats/sessions/${sessionSlug}/chat/stream`, {
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
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') return;
          try {
            const parsed = JSON.parse(data);
            if (parsed.choices?.[0]?.delta?.content) {
              onChunk?.(parsed.choices[0].delta.content);
            }
          } catch {
            // skip parse errors
          }
        }
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
