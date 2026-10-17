import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './theme/app.css';
import './theme/global.css';
import './i18n';
import { App } from './App';
import { Providers } from './Providers';
import { ErrorBoundary } from './components/ErrorBoundary';
import { reloadForNewBuild } from './lib/buildReload';
import { applyStoredPreferences, openDetailsForPrint } from './lib/preferences';

applyStoredPreferences();
openDetailsForPrint();

// A chunk of the previous build failed to load (the app was redeployed while this tab was open): reload once to get
// the current build. The error itself still reaches the ErrorBoundary, which shows a reload button if this fails.
window.addEventListener('vite:preloadError', () => {
  reloadForNewBuild();
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Providers>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </Providers>
  </StrictMode>,
);
