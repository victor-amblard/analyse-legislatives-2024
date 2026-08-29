/**
 * Deux langues, le français par défaut.
 *
 * « Par défaut » veut dire : le français est servi à la racine (`/`), l'anglais
 * sur `/en/`. Un visiteur qui arrive sans préciser tombe donc sur le français,
 * et l'anglais est une destination explicite — pas l'inverse.
 */
export const DEFAULT_LOCALE = 'fr' as const;
export type Locale = 'fr' | 'en';

export const LOCALES: Locale[] = ['fr', 'en'];

/** Racine du site pour une langue donnée. */
export function pathFor(locale: Locale): string {
  return locale === DEFAULT_LOCALE ? '/' : `/${locale}/`;
}

export const UI: Record<Locale, { name: string; switchTo: string; tocTitle: string }> = {
  fr: { name: 'Français', switchTo: 'Read in English', tocTitle: 'Sommaire' },
  en: { name: 'English', switchTo: 'Lire en français', tocTitle: 'Contents' },
};
