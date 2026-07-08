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

    "campaign.report.title": "Email Report",
    "campaign.report.description": "Email activity metrics for this campaign.",
    "campaign.report.start_date": "From",
    "campaign.report.end_date": "To",
    "campaign.report.generate": "Generate",
    "campaign.report.error": "Unable to retrieve the report",
    "campaign.report.empty_title": "No report yet",
    "campaign.report.empty_description": "Pick a date range and generate the report.",
    "campaign.report.dispositions": "Dispositions",
    "campaign.report.disposition_name": "Disposition",
    "campaign.report.total": "Total",
    "campaign.report.not_disposed": "Not dispositioned",
    "campaign.report.correos_recibidos": "Emails received",
    "campaign.report.correos_enviados": "Emails sent",
    "campaign.report.correos_fallidos": "Failed emails",
    "campaign.report.conversaciones_iniciadas": "Conversations started",
    "campaign.report.conversaciones_atendidas": "Conversations attended",
    "campaign.report.conversaciones_sin_atender": "Conversations unattended",
    "campaign.report.conversaciones_respondidas": "Conversations answered",
    "campaign.report.conversaciones_reabiertas": "Conversations reopened",
    "campaign.report.conversaciones_calificadas": "Conversations dispositioned",
    "campaign.report.conversaciones_sin_calificar": "Conversations not dispositioned",

    "campaign.conversations.title": "Email Conversations",
    "campaign.conversations.description": "Email conversations for this campaign.",
    "campaign.conversations.start_date": "From",
    "campaign.conversations.end_date": "To",
    "campaign.conversations.email": "User email",
    "campaign.conversations.email_placeholder": "Filter by address…",
    "campaign.conversations.agent": "Agent",
    "campaign.conversations.all_agents": "All agents",
    "campaign.conversations.no_agent": "Unassigned",
    "campaign.conversations.search": "Search",
    "campaign.conversations.error": "Unable to retrieve the conversations",
    "campaign.conversations.col_agent": "Agent",
    "campaign.conversations.col_start": "Started",
    "campaign.conversations.col_subject": "Subject",
    "campaign.conversations.col_email": "User email",
    "campaign.conversations.col_account": "Account",
    "campaign.conversations.col_last": "Last interaction",
    "campaign.conversations.col_status": "Status",
    "campaign.conversations.col_emails": "Emails",
    "campaign.conversations.col_disposition": "Disposition",
    "campaign.conversations.col_options": "Options",
    "campaign.conversations.empty_title": "No conversations found",
    "campaign.conversations.empty_description": "No conversations match these filters.",
    "campaign.conversations.prompt_title": "Search conversations",
    "campaign.conversations.prompt_description": "Set the filters and press Search.",
    "campaign.conversations.detail_title": "Conversation detail",
    "campaign.conversations.inbound": "Incoming",
    "campaign.conversations.outbound": "Outgoing",
    "campaign.conversations.status.new": "New",
    "campaign.conversations.status.assigned": "Assigned",
    "campaign.conversations.status.in_progress": "In progress",
    "campaign.conversations.status.answered": "Answered",
    "campaign.conversations.status.reopened": "Reopened",
    "campaign.conversations.status.closed": "Closed",
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

    "campaign.report.title": "Reporte de Email",
    "campaign.report.description": "Métricas de actividad de correo de esta campaña.",
    "campaign.report.start_date": "Desde",
    "campaign.report.end_date": "Hasta",
    "campaign.report.generate": "Generar",
    "campaign.report.error": "No se pudo obtener el reporte",
    "campaign.report.empty_title": "Aún no hay reporte",
    "campaign.report.empty_description": "Elija un rango de fechas y genere el reporte.",
    "campaign.report.dispositions": "Calificaciones",
    "campaign.report.disposition_name": "Calificación",
    "campaign.report.total": "Total",
    "campaign.report.not_disposed": "Sin calificar",
    "campaign.report.correos_recibidos": "Correos recibidos",
    "campaign.report.correos_enviados": "Correos enviados",
    "campaign.report.correos_fallidos": "Correos fallidos",
    "campaign.report.conversaciones_iniciadas": "Conversaciones iniciadas",
    "campaign.report.conversaciones_atendidas": "Conversaciones atendidas",
    "campaign.report.conversaciones_sin_atender": "Conversaciones sin atender",
    "campaign.report.conversaciones_respondidas": "Conversaciones respondidas",
    "campaign.report.conversaciones_reabiertas": "Conversaciones reabiertas",
    "campaign.report.conversaciones_calificadas": "Conversaciones calificadas",
    "campaign.report.conversaciones_sin_calificar": "Conversaciones sin calificar",

    "campaign.conversations.title": "Conversaciones de Email",
    "campaign.conversations.description": "Conversaciones de correo de esta campaña.",
    "campaign.conversations.start_date": "Desde",
    "campaign.conversations.end_date": "Hasta",
    "campaign.conversations.email": "Email del usuario",
    "campaign.conversations.email_placeholder": "Filtrar por dirección…",
    "campaign.conversations.agent": "Agente",
    "campaign.conversations.all_agents": "Todos los agentes",
    "campaign.conversations.no_agent": "Sin agente",
    "campaign.conversations.search": "Buscar",
    "campaign.conversations.error": "No se pudieron obtener las conversaciones",
    "campaign.conversations.col_agent": "Agente",
    "campaign.conversations.col_start": "Inicio",
    "campaign.conversations.col_subject": "Asunto",
    "campaign.conversations.col_email": "Email del usuario",
    "campaign.conversations.col_account": "Cuenta",
    "campaign.conversations.col_last": "Última interacción",
    "campaign.conversations.col_status": "Estado",
    "campaign.conversations.col_emails": "Correos",
    "campaign.conversations.col_disposition": "Calificación",
    "campaign.conversations.col_options": "Opciones",
    "campaign.conversations.empty_title": "No se encontraron conversaciones",
    "campaign.conversations.empty_description": "Ninguna conversación coincide con estos filtros.",
    "campaign.conversations.prompt_title": "Buscar conversaciones",
    "campaign.conversations.prompt_description": "Configure los filtros y presione Buscar.",
    "campaign.conversations.detail_title": "Detalle de la conversación",
    "campaign.conversations.inbound": "Entrante",
    "campaign.conversations.outbound": "Saliente",
    "campaign.conversations.status.new": "Nuevo",
    "campaign.conversations.status.assigned": "Asignado",
    "campaign.conversations.status.in_progress": "En gestión",
    "campaign.conversations.status.answered": "Respondido",
    "campaign.conversations.status.reopened": "Reabierto",
    "campaign.conversations.status.closed": "Cerrado",
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

    "campaign.report.title": "Relatório de E-mail",
    "campaign.report.description": "Métricas de atividade de e-mail desta campanha.",
    "campaign.report.start_date": "De",
    "campaign.report.end_date": "Até",
    "campaign.report.generate": "Gerar",
    "campaign.report.error": "Não foi possível obter o relatório",
    "campaign.report.empty_title": "Ainda não há relatório",
    "campaign.report.empty_description": "Escolha um intervalo de datas e gere o relatório.",
    "campaign.report.dispositions": "Qualificações",
    "campaign.report.disposition_name": "Qualificação",
    "campaign.report.total": "Total",
    "campaign.report.not_disposed": "Sem qualificação",
    "campaign.report.correos_recibidos": "E-mails recebidos",
    "campaign.report.correos_enviados": "E-mails enviados",
    "campaign.report.correos_fallidos": "E-mails com falha",
    "campaign.report.conversaciones_iniciadas": "Conversas iniciadas",
    "campaign.report.conversaciones_atendidas": "Conversas atendidas",
    "campaign.report.conversaciones_sin_atender": "Conversas não atendidas",
    "campaign.report.conversaciones_respondidas": "Conversas respondidas",
    "campaign.report.conversaciones_reabiertas": "Conversas reabertas",
    "campaign.report.conversaciones_calificadas": "Conversas qualificadas",
    "campaign.report.conversaciones_sin_calificar": "Conversas sem qualificação",

    "campaign.conversations.title": "Conversas de E-mail",
    "campaign.conversations.description": "Conversas de e-mail desta campanha.",
    "campaign.conversations.start_date": "De",
    "campaign.conversations.end_date": "Até",
    "campaign.conversations.email": "E-mail do usuário",
    "campaign.conversations.email_placeholder": "Filtrar por endereço…",
    "campaign.conversations.agent": "Agente",
    "campaign.conversations.all_agents": "Todos os agentes",
    "campaign.conversations.no_agent": "Sem agente",
    "campaign.conversations.search": "Buscar",
    "campaign.conversations.error": "Não foi possível obter as conversas",
    "campaign.conversations.col_agent": "Agente",
    "campaign.conversations.col_start": "Início",
    "campaign.conversations.col_subject": "Assunto",
    "campaign.conversations.col_email": "E-mail do usuário",
    "campaign.conversations.col_account": "Conta",
    "campaign.conversations.col_last": "Última interação",
    "campaign.conversations.col_status": "Status",
    "campaign.conversations.col_emails": "E-mails",
    "campaign.conversations.col_disposition": "Qualificação",
    "campaign.conversations.col_options": "Opções",
    "campaign.conversations.empty_title": "Nenhuma conversa encontrada",
    "campaign.conversations.empty_description": "Nenhuma conversa corresponde a esses filtros.",
    "campaign.conversations.prompt_title": "Buscar conversas",
    "campaign.conversations.prompt_description": "Defina os filtros e pressione Buscar.",
    "campaign.conversations.detail_title": "Detalhe da conversa",
    "campaign.conversations.inbound": "Recebido",
    "campaign.conversations.outbound": "Enviado",
    "campaign.conversations.status.new": "Novo",
    "campaign.conversations.status.assigned": "Atribuído",
    "campaign.conversations.status.in_progress": "Em andamento",
    "campaign.conversations.status.answered": "Respondido",
    "campaign.conversations.status.reopened": "Reaberto",
    "campaign.conversations.status.closed": "Fechado",
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

    "campaign.report.title": "گزارش ایمیل",
    "campaign.report.description": "معیارهای فعالیت ایمیل این کمپین.",
    "campaign.report.start_date": "از",
    "campaign.report.end_date": "تا",
    "campaign.report.generate": "تولید",
    "campaign.report.error": "دریافت گزارش ممکن نشد",
    "campaign.report.empty_title": "هنوز گزارشی وجود ندارد",
    "campaign.report.empty_description": "یک بازه زمانی انتخاب کنید و گزارش را تولید کنید.",
    "campaign.report.dispositions": "ارزیابی‌ها",
    "campaign.report.disposition_name": "ارزیابی",
    "campaign.report.total": "مجموع",
    "campaign.report.not_disposed": "بدون ارزیابی",
    "campaign.report.correos_recibidos": "ایمیل‌های دریافتی",
    "campaign.report.correos_enviados": "ایمیل‌های ارسالی",
    "campaign.report.correos_fallidos": "ایمیل‌های ناموفق",
    "campaign.report.conversaciones_iniciadas": "مکالمات آغازشده",
    "campaign.report.conversaciones_atendidas": "مکالمات رسیدگی‌شده",
    "campaign.report.conversaciones_sin_atender": "مکالمات رسیدگی‌نشده",
    "campaign.report.conversaciones_respondidas": "مکالمات پاسخ‌داده‌شده",
    "campaign.report.conversaciones_reabiertas": "مکالمات بازگشایی‌شده",
    "campaign.report.conversaciones_calificadas": "مکالمات ارزیابی‌شده",
    "campaign.report.conversaciones_sin_calificar": "مکالمات بدون ارزیابی",

    "campaign.conversations.title": "مکالمات ایمیل",
    "campaign.conversations.description": "مکالمات ایمیل این کمپین.",
    "campaign.conversations.start_date": "از",
    "campaign.conversations.end_date": "تا",
    "campaign.conversations.email": "ایمیل کاربر",
    "campaign.conversations.email_placeholder": "فیلتر بر اساس نشانی…",
    "campaign.conversations.agent": "اپراتور",
    "campaign.conversations.all_agents": "همه اپراتورها",
    "campaign.conversations.no_agent": "بدون اپراتور",
    "campaign.conversations.search": "جستجو",
    "campaign.conversations.error": "دریافت مکالمات ممکن نشد",
    "campaign.conversations.col_agent": "اپراتور",
    "campaign.conversations.col_start": "شروع",
    "campaign.conversations.col_subject": "موضوع",
    "campaign.conversations.col_email": "ایمیل کاربر",
    "campaign.conversations.col_account": "حساب",
    "campaign.conversations.col_last": "آخرین تعامل",
    "campaign.conversations.col_status": "وضعیت",
    "campaign.conversations.col_emails": "ایمیل‌ها",
    "campaign.conversations.col_disposition": "ارزیابی",
    "campaign.conversations.col_options": "گزینه‌ها",
    "campaign.conversations.empty_title": "مکالمه‌ای یافت نشد",
    "campaign.conversations.empty_description": "هیچ مکالمه‌ای با این فیلترها مطابقت ندارد.",
    "campaign.conversations.prompt_title": "جستجوی مکالمات",
    "campaign.conversations.prompt_description": "فیلترها را تنظیم کنید و جستجو را بزنید.",
    "campaign.conversations.detail_title": "جزئیات مکالمه",
    "campaign.conversations.inbound": "ورودی",
    "campaign.conversations.outbound": "خروجی",
    "campaign.conversations.status.new": "جدید",
    "campaign.conversations.status.assigned": "تخصیص‌یافته",
    "campaign.conversations.status.in_progress": "در حال انجام",
    "campaign.conversations.status.answered": "پاسخ‌داده‌شده",
    "campaign.conversations.status.reopened": "بازگشایی‌شده",
    "campaign.conversations.status.closed": "بسته‌شده",
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
