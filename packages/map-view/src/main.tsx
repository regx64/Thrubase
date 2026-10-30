import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import * as Thrubase from './index';
import { App } from './App';
import { MapOnly } from './MapOnly';
import { createTransport } from './transport';
import type { Lang } from './types';
import './tokens.css';
import './styles.css';

declare global {
  interface Window {
    Thrubase: typeof Thrubase;
    __THRUBASE_LANG__?: string;
    __THRUBASE_MODE__?: 'panel' | 'map';
  }
}

window.Thrubase = Thrubase;

const guess = (window.__THRUBASE_LANG__ ?? navigator.language ?? 'en').toLowerCase();
const lang: Lang = guess.startsWith('ko') ? 'ko' : 'en';
const transport = createTransport();
const root = document.getElementById('root');
if (root) {
  createRoot(root).render(
    <StrictMode>
      {window.__THRUBASE_MODE__ === 'map' ? <MapOnly transport={transport} lang={lang} /> : <App transport={transport} initialLang={lang} />}
    </StrictMode>,
  );
}
