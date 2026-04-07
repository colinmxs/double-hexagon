import { createI18n } from 'vue-i18n'
import en from './locales/en.json'
import es from './locales/es.json'

type MessageSchema = typeof en

const SUPPORTED_LOCALES = ['en', 'es'] as const
type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]

function isSupportedLocale(locale: string): locale is SupportedLocale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(locale)
}

function detectBrowserLocale(): SupportedLocale {
  const stored = localStorage.getItem('locale')
  if (stored && isSupportedLocale(stored)) {
    return stored
  }

  const browserLang = navigator.language.split('-')[0]
  if (isSupportedLocale(browserLang)) {
    return browserLang
  }

  return 'en'
}

const i18n = createI18n<[MessageSchema], SupportedLocale>({
  legacy: false,
  locale: detectBrowserLocale(),
  fallbackLocale: 'en',
  messages: {
    en,
    es,
  },
})

export { SUPPORTED_LOCALES, type SupportedLocale, isSupportedLocale }
export default i18n
