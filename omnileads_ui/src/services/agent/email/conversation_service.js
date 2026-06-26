import URLS from '@/api_urls/agent/email/conversation_urls';
import { BaseService, HTTP } from '@/services/base_service';

export default class EmailConversationService extends BaseService {
    constructor () {
        super(URLS, 'Email <Conversation>');
    }

    // References-first: a single lightweight call for the whole inbox.
    async getInbox () {
        try {
            this.initPayload();
            const resp = await fetch(this.urls.Inbox(), this.payload);
            return await resp.json();
        } catch (error) {
            console.error('Error al obtener < Inbox de Email >');
            return null;
        } finally {
            this.initPayload();
        }
    }

    // Thread-on-click: the full message thread is only loaded on demand.
    async getConversationDetail (id) {
        try {
            this.initPayload();
            const resp = await fetch(this.urls.Detail(id), this.payload);
            return await resp.json();
        } catch (error) {
            console.error('Error al obtener < Detalle de la Conversacion de Email >');
            return null;
        } finally {
            this.initPayload();
        }
    }

    async attend (id) {
        try {
            this.setPayload(HTTP.POST, JSON.stringify({}));
            const resp = await fetch(this.urls.Attend(id), this.payload);
            return await resp.json();
        } catch (error) {
            console.error('Error al asignar la conversacion de Email');
            return null;
        } finally {
            this.initPayload();
        }
    }

    async release (id) {
        try {
            this.setPayload(HTTP.POST, JSON.stringify({}));
            const resp = await fetch(this.urls.Release(id), this.payload);
            return resp.ok;
        } catch (error) {
            console.error('Error al desasignar la conversacion de Email');
            return false;
        } finally {
            this.initPayload();
        }
    }

    async markAsRead (id) {
        try {
            this.setPayload(HTTP.POST, JSON.stringify({}));
            await fetch(this.urls.MarkAsRead(id), this.payload);
        } catch (error) {
            console.error('Error al marcar como leido');
        } finally {
            this.initPayload();
        }
    }

    // mode: 'unassign' | 'keep' | 'dispose'. formData carries body_text/body_html,
    // mode and any attachments (multipart).
    async reply (id, formData) {
        try {
            this.setPayload(HTTP.POST, formData, true);
            const resp = await fetch(this.urls.Reply(id), this.payload);
            const body = await resp.json().catch(() => ({}));
            return { ok: resp.ok, body };
        } catch (error) {
            console.error('Error al responder el Email');
            return { ok: false, body: {} };
        } finally {
            this.initPayload();
        }
    }

    async getDispositionOptions (id) {
        try {
            this.initPayload();
            const resp = await fetch(this.urls.DispositionOptions(id), this.payload);
            return await resp.json();
        } catch (error) {
            console.error('Error al obtener las opciones de calificacion');
            return [];
        } finally {
            this.initPayload();
        }
    }

    async disposition (id, data) {
        try {
            this.setPayload(HTTP.POST, JSON.stringify(data));
            const resp = await fetch(this.urls.Disposition(id), this.payload);
            const body = await resp.json().catch(() => ({}));
            return { ok: resp.ok, body };
        } catch (error) {
            console.error('Error al calificar la conversacion');
            return { ok: false, body: {} };
        } finally {
            this.initPayload();
        }
    }

    async getContactFields (id) {
        try {
            this.initPayload();
            const resp = await fetch(this.urls.ContactFields(id), this.payload);
            return await resp.json();
        } catch (error) {
            console.error('Error al obtener los campos de contacto');
            return [];
        } finally {
            this.initPayload();
        }
    }

    async createContact (id, data) {
        try {
            this.setPayload(HTTP.POST, JSON.stringify(data));
            const resp = await fetch(this.urls.Contact(id), this.payload);
            return await resp.json();
        } catch (error) {
            console.error('Error al guardar el contacto');
            return null;
        } finally {
            this.initPayload();
        }
    }
}
