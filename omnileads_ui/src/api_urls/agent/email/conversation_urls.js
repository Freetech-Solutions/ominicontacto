// Agent email channel endpoints. Mounted at /email/api/v1/ (NOT /api/v1/whatsapp).
const BASE_ROUTE = '/email/api/v1/conversations';

export default {
    // Lightweight conversation REFERENCES grouped in tabs:
    // { assigned, general: { new, waiting_client } }
    Inbox: () => `${BASE_ROUTE}`,
    // Full thread — only fetched when the agent opens a conversation.
    Detail: (id) => `${BASE_ROUTE}/${id}`,
    Attend: (id) => `${BASE_ROUTE}/${id}/attend`,
    // Desasignar: devuelve el correo a la cola general como NUEVO (sin responder).
    Release: (id) => `${BASE_ROUTE}/${id}/release`,
    MarkAsRead: (id) => `${BASE_ROUTE}/${id}/mark_as_read`,
    Reply: (id) => `${BASE_ROUTE}/${id}/reply`,
    DispositionOptions: (id) => `${BASE_ROUTE}/${id}/disposition_options`,
    Disposition: (id) => `${BASE_ROUTE}/${id}/disposition`,
    ContactFields: (id) => `${BASE_ROUTE}/${id}/contact_fields`,
    Contact: (id) => `${BASE_ROUTE}/${id}/contact`
};
