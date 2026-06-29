// Lightweight i18n for the webui.
//
// The webui has no i18n framework and is served as a static SPA embedded by the
// legacy Django console. Rather than pull a new dependency (the build runs
// `pnpm install --frozen-lockfile`, so a new dep would break it without a
// regenerated lockfile), this module reads the language the user already picked
// in Django (the `django_language` cookie, same origin) and resolves message
// keys against per-locale dictionaries. Drop-in replaceable by vue-i18n later.
import Cookies from "universal-cookie"

export type Locale = "en" | "es" | "pt-br" | "fa"

type Messages = Record<string, string>

const messages: Record<Locale, Messages> = {
  en: {
    "account.purge.button": "Delete history",
    "account.purge.title": "Are you sure?",
    "account.purge.description":
      "Are you sure you want to delete all the history? This will NOT delete anything "
      + "from the IMAP server; it only removes the local data and re-downloads the inbox "
      + "from the SINCE date. Warning! it may consume resources — do it outside production.",
    "account.purge.confirm": "Delete history",
    "account.purge.cancel": "Cancel",
    "account.purge.success":
      "History deleted; the inbox will be re-downloaded from the SINCE date.",
    "account.purge.error": "Could not delete the history.",
  },
  es: {
    "account.purge.button": "Eliminar histórico",
    "account.purge.title": "¿Está seguro?",
    "account.purge.description":
      "¿Está seguro que desea eliminar todos los históricos? Esto no eliminará nada del "
      + "servidor IMAP, sólo borrará los datos locales y descargará nuevamente el inbox "
      + "desde la fecha SINCE. ¡Ojo! puede consumir recursos, hágalo fuera de producción.",
    "account.purge.confirm": "Eliminar histórico",
    "account.purge.cancel": "Cancelar",
    "account.purge.success":
      "Histórico eliminado; el inbox se re-descargará desde la fecha SINCE.",
    "account.purge.error": "No se pudo eliminar el histórico.",
  },
  "pt-br": {
    "account.purge.button": "Excluir histórico",
    "account.purge.title": "Tem certeza?",
    "account.purge.description":
      "Tem certeza de que deseja excluir todo o histórico? Isso NÃO excluirá nada do "
      + "servidor IMAP; apenas remove os dados locais e baixa novamente a caixa de entrada "
      + "a partir da data SINCE. Atenção! pode consumir recursos — faça isso fora de produção.",
    "account.purge.confirm": "Excluir histórico",
    "account.purge.cancel": "Cancelar",
    "account.purge.success":
      "Histórico excluído; a caixa de entrada será baixada novamente a partir da data SINCE.",
    "account.purge.error": "Não foi possível excluir o histórico.",
  },
  fa: {
    "account.purge.button": "حذف تاریخچه",
    "account.purge.title": "آیا مطمئن هستید؟",
    "account.purge.description":
      "آیا مطمئن هستید که می‌خواهید کل تاریخچه را حذف کنید؟ این کار چیزی را از سرور IMAP "
      + "حذف نمی‌کند؛ فقط داده‌های محلی را پاک می‌کند و صندوق ورودی را از تاریخ SINCE دوباره "
      + "دانلود می‌کند. هشدار! ممکن است منابع زیادی مصرف کند — خارج از محیط تولید انجام دهید.",
    "account.purge.confirm": "حذف تاریخچه",
    "account.purge.cancel": "انصراف",
    "account.purge.success":
      "تاریخچه حذف شد؛ صندوق ورودی از تاریخ SINCE دوباره دانلود می‌شود.",
    "account.purge.error": "حذف تاریخچه ممکن نشد.",
  },
}

function detectLocale(): Locale {
  try {
    const raw = String(new Cookies().get("django_language") || "")
      .toLowerCase()
      .replace("_", "-")
    if (raw.startsWith("es")) return "es"
    if (raw.startsWith("pt")) return "pt-br"
    if (raw.startsWith("fa")) return "fa"
  } catch {
    // no cookie / not available -> fall back to English
  }
  return "en"
}

export const locale: Locale = detectLocale()

export function t(key: string): string {
  return messages[locale][key] ?? messages.en[key] ?? key
}
