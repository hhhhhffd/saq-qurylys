import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './theme/app.css';
import './theme/global.css';
import './i18n';
import { App } from './App';
import { Providers } from './Providers';
import { applyStoredPreferences, openDetailsForPrint } from './lib/preferences';

applyStoredPreferences();
openDetailsForPrint();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Providers>
      <App />
    </Providers>
  </StrictMode>,
);
