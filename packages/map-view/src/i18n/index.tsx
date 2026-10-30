import { createContext, useCallback, useContext, type ReactNode } from 'react';
import en from './en.json';
import ko from './ko.json';
import type { Lang } from '../types';

export const messages: Record<Lang, Record<string, string>> = { en, ko };

export function translate(lang: Lang, key: string, params: Record<string, string | number> = {}): string {
  const template = messages[lang][key] ?? messages.en[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (m, name: string) => (name in params ? String(params[name]) : m));
}

const LangContext = createContext<Lang>('en');

export function LangProvider({ lang, children }: { lang: Lang; children: ReactNode }) {
  return <LangContext.Provider value={lang}>{children}</LangContext.Provider>;
}

export function useLang(): Lang {
  return useContext(LangContext);
}

export function useT() {
  const lang = useLang();
  return useCallback((key: string, params?: Record<string, string | number>) => translate(lang, key, params), [lang]);
}
