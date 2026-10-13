import { useState } from 'react';

import { useAuth } from './hooks/useAuth';
import Layout from './components/Layout';
import DashboardPage from './pages/DashboardPage';
import ProjectsPage from './pages/ProjectsPage';
import SessionPage from './pages/SessionPage';
import SearchPage from './pages/SearchPage';
import AdminPage from './pages/AdminPage';
import LoginPage from './pages/LoginPage';

const googleNotice = new URLSearchParams(window.location.search).get('google') || undefined;
if (googleNotice) window.history.replaceState(null, '', '/');

export type Page = 'dashboard' | 'chat' | 'projects' | 'session' | 'search' | 'settings';

export default function App() {
  const { authenticated, loading, logout, check } = useAuth();
  const [currentPage, setCurrentPage] = useState<Page>(googleNotice ? 'settings' : 'dashboard');
  const [pageProps, setPageProps] = useState<{ sessionId?: string; projectSlug?: string }>({});

  function navigate(page: Page, props?: { sessionId?: string; projectSlug?: string }) {
    setCurrentPage(page);
    setPageProps(props || {});
    window.scrollTo(0, 0);
  }

  if (loading) {
    return <div className="login-wrap"><div className="muted">Loading…</div></div>;
  }

  if (!authenticated) {
    return <LoginPage onLogin={() => { check(); navigate('dashboard'); }} />;
  }

  return (
    <Layout current={currentPage} onNavigate={navigate} onLogout={() => { logout(); navigate('dashboard'); }}>
      {currentPage === 'dashboard' && <DashboardPage onNavigate={navigate} />}
      {currentPage === 'chat' && <SessionPage key="home" />}
      {currentPage === 'session' && (
        <SessionPage key={pageProps.projectSlug || 'home'} sessionId={pageProps.sessionId} projectSlug={pageProps.projectSlug} />
      )}
      {currentPage === 'projects' && <ProjectsPage onNavigate={navigate} />}
      {currentPage === 'search' && <SearchPage />}
      {currentPage === 'settings' && <AdminPage notice={googleNotice} />}
    </Layout>
  );
}
