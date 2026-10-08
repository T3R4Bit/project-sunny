import { useState } from 'react';
import { useAuth } from './hooks/useAuth';
import Header from './components/Header';
import HomePage from './pages/HomePage';
import ProjectsPage from './pages/ProjectsPage';
import SessionPage from './pages/SessionPage';
import SearchPage from './pages/SearchPage';
import AdminPage from './pages/AdminPage';
import LoginPage from './pages/LoginPage';

export type Page = 'home' | 'projects' | 'session' | 'search' | 'admin';

export default function App() {
  const { authenticated, loading, logout } = useAuth();
  const [currentPage, setCurrentPage] = useState<Page>('home');
  const [pageProps, setPageProps] = useState<{ sessionId?: string; projectSlug?: string }>({});

  function navigate(page: Page, props?: { sessionId?: string; projectSlug?: string }) {
    setCurrentPage(page);
    setPageProps(props || {});
  }

  function handleLogout() {
    logout();
    navigate('home');
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <div className="mono">Loading Sunny...</div>
      </div>
    );
  }

  if (!authenticated) {
    return (
      <div>
        <LoginPage onNavigate={(page: string) => navigate(page as Page)} />
      </div>
    );
  }

  return (
    <div className="app">
      <Header
        currentPage={currentPage}
        onNavigate={(page: string) => navigate(page as Page)}
        onLogout={handleLogout}
      />
      <main className="container" style={{ padding: '16px' }}>
        {currentPage === 'home' && <HomePage />}
        {currentPage === 'projects' && <ProjectsPage onNavigate={navigate} />}
        {currentPage === 'session' && (
          <SessionPage
            sessionId={pageProps.sessionId}
            projectSlug={pageProps.projectSlug}
          />
        )}
        {currentPage === 'search' && <SearchPage />}
        {currentPage === 'admin' && <AdminPage />}
      </main>
    </div>
  );
}
