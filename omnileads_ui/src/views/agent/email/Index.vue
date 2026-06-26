<template>
  <div class="email-agent-panel" :class="{ reading: !!active }">
    <Toast />

    <!-- Header — same Toolbar treatment as the other channels -->
    <Toolbar class="email-toolbar mb-2" :style="{ border: `4px solid ${email_color}` }">
      <template #start>
        <i class="pi pi-envelope mr-2" :style="{ color: email_color, 'font-size': '3rem' }"></i>
        <h2 class="font-bold m-0">Email</h2>
      </template>
      <template #end>
        <Button
          icon="pi pi-refresh"
          class="p-button-secondary mr-2"
          @click="loadInbox"
          v-tooltip.bottom="'Actualizar'"
        />
        <Button
          v-if="active"
          :icon="isFullscreen ? 'pi pi-window-minimize' : 'pi pi-window-maximize'"
          class="p-button-secondary mr-2"
          @click="toggleFullscreen"
          v-tooltip.bottom="isFullscreen ? 'Restaurar' : 'Pantalla completa'"
        />
        <Button
          icon="pi pi-times"
          class="p-button-danger"
          @click="active ? closeThread() : closePanel()"
          v-tooltip.bottom="active ? 'Volver al inbox' : 'Cerrar'"
        />
      </template>
    </Toolbar>

    <!-- INBOX (references only — Thunderbird-style dense list) -->
    <div v-if="!active" class="inbox-body">
      <TabView v-model:activeIndex="activeTab">
        <TabPanel>
          <template #header>
            <span>Asignado</span>
            <Badge :value="inbox.assigned.length.toString()" class="ml-2" severity="secondary" />
          </template>
          <div class="list">
            <ConversationInfo
              v-for="c in inbox.assigned"
              :key="c.id"
              :conversation="c"
              context="assigned"
              @open="open"
            />
            <div v-if="inbox.assigned.length === 0" class="empty">Sin conversaciones asignadas</div>
          </div>
        </TabPanel>

        <TabPanel>
          <template #header>
            <span>Nuevo / Reabierto</span>
            <Badge :value="inbox.general.new.length.toString()" class="ml-2" severity="secondary" />
          </template>
          <div class="list">
            <ConversationInfo
              v-for="c in inbox.general.new"
              :key="c.id"
              :conversation="c"
              context="general"
              @open="open"
              @take="attend"
            />
            <div v-if="inbox.general.new.length === 0" class="empty">Sin correos nuevos</div>
          </div>
        </TabPanel>

        <TabPanel>
          <template #header>
            <span>Esperando al cliente</span>
            <Badge :value="inbox.general.waiting_client.length.toString()" class="ml-2" severity="secondary" />
          </template>
          <div class="list">
            <ConversationInfo
              v-for="c in inbox.general.waiting_client"
              :key="c.id"
              :conversation="c"
              context="general"
              @open="open"
              @take="attend"
            />
            <div v-if="inbox.general.waiting_client.length === 0" class="empty">Sin correos esperando respuesta del cliente</div>
          </div>
        </TabPanel>
      </TabView>
    </div>

    <!-- THREAD (large reading view, opened on click/take) -->
    <div v-else class="email-thread">
      <div class="thread-head">
        <div class="thread-title">{{ active.subject || '(sin asunto)' }}</div>
        <div class="thread-sub">
          <span><i class="pi pi-user"></i> {{ active.client_name || active.client_mail }}</span>
          <span class="campaign"><i class="pi pi-sitemap"></i> {{ active.campaign_name || '-----' }}</span>
          <span class="head-actions">
            <Button label="Datos de contacto" icon="pi pi-user-edit" class="p-button-text p-button-sm" @click="openContactForm" />
            <Button label="Calificar" icon="pi pi-tag" class="p-button-text p-button-sm" @click="openDisposition" v-tooltip.bottom="'Calificar y cerrar la conversación'" />
            <Button label="Desasignar" icon="pi pi-undo" class="p-button-text p-button-sm" :disabled="releasing" @click="releaseConversation" v-tooltip.bottom="'Devolver a la cola como nuevo'" />
          </span>
        </div>
      </div>

      <div class="msgs">
        <div
          v-for="m in active.mensajes"
          :key="m.id"
          class="msg-line"
          :class="m.direction === 'outbound' ? 'out' : 'in'"
        >
          <div class="bubble" :class="m.direction === 'outbound' ? 'bubble-out' : 'bubble-in'">
            <div class="bubble-head">
              <span class="bubble-from">
                {{ m.direction === 'outbound' ? (m.from_name || 'Agente') : (m.from_name || m.from_mail) }}
              </span>
              <span class="bubble-date">{{ fmtDate(m.date) }}</span>
            </div>
            <!-- eslint-disable-next-line vue/no-v-html -->
            <div class="bubble-body" v-html="m.body_html || m.body_text"></div>
            <div v-if="m.attachments && m.attachments.length" class="bubble-attachments">
              <a v-for="a in m.attachments" :key="a.cid || a.name" :href="a.url" target="_blank" class="attachment">
                <i class="pi pi-paperclip"></i> {{ a.name }}
              </a>
            </div>
          </div>
        </div>
      </div>

      <!-- Composer — basic mail-client layout -->
      <div class="composer">
        <div class="composer-fields">
          <div class="cfield">
            <label>Para</label>
            <InputText :modelValue="active.client_mail" disabled class="w-full" />
          </div>
          <div class="cfield" v-if="showCc">
            <label>CC</label>
            <InputText v-model="cc" class="w-full" placeholder="separar con comas" />
          </div>
          <div class="cfield" v-if="showCc">
            <label>CCO</label>
            <InputText v-model="bcc" class="w-full" placeholder="separar con comas" />
          </div>
          <div class="cfield">
            <label>Asunto</label>
            <InputText :modelValue="replySubject" disabled class="w-full" />
          </div>
        </div>

        <Editor v-model="replyHtml" editorStyle="height: 180px" class="body-box" @load="onEditorLoad">
          <template #toolbar>
            <span class="ql-formats">
              <button class="ql-bold" type="button"></button>
              <button class="ql-italic" type="button"></button>
              <button class="ql-underline" type="button"></button>
            </span>
            <span class="ql-formats">
              <select class="ql-color"></select>
              <select class="ql-background"></select>
            </span>
            <span class="ql-formats">
              <button class="ql-list" value="ordered" type="button"></button>
              <button class="ql-list" value="bullet" type="button"></button>
            </span>
            <span class="ql-formats">
              <button class="ql-link" type="button"></button>
              <button class="ql-clean" type="button"></button>
            </span>
          </template>
        </Editor>
        <input ref="files" type="file" multiple class="hidden-file" @change="onFilesChange" />

        <div class="composer-bar">
          <Button label="Adjuntar archivos" icon="pi pi-paperclip" class="p-button-text p-button-sm" @click="$refs.files.click()" />
          <Button v-if="!showCc" label="CC / CCO" icon="pi pi-users" class="p-button-text p-button-sm" @click="showCc = true" />
          <div class="emoji-wrap">
            <Button label="😊 Emojis" class="p-button-text p-button-sm" @click="showEmoji = !showEmoji" />
            <div v-if="showEmoji" class="emoji-palette">
              <button
                v-for="em in emojis"
                :key="em"
                type="button"
                class="emoji-item"
                @click="insertEmoji(em)"
              >{{ em }}</button>
            </div>
          </div>
          <span v-if="attachmentNames.length" class="attach-names">{{ attachmentNames.length }}: {{ attachmentNames.join(', ') }}</span>
          <span class="spacer"></span>
          <div class="send-group">
            <Button label="Responder y Desasignar" icon="pi pi-reply" class="p-button-outlined p-button-sm" :disabled="sending || !hasBody" @click="reply('unassign')" />
            <Button label="Responder y Seguir gestionando" icon="pi pi-send" class="p-button-sm" :disabled="sending || !hasBody" @click="reply('keep')" />
            <Button label="Responder y Calificar" icon="pi pi-check" class="p-button-success p-button-sm" :disabled="sending || !hasBody" @click="reply('dispose')" />
          </div>
        </div>
      </div>
    </div>

    <!-- Guardar contacto en BD -->
    <Dialog v-model:visible="showContact" modal header="Guardar contacto" :style="{ width: '460px' }">
      <div v-for="f in visibleContactFields" :key="f.name" class="field">
        <label>{{ f.name }}<span v-if="f.mandatory"> *</span></label>
        <InputText v-model="contactData[f.name]" :disabled="f.block" class="w-full" />
      </div>
      <template #footer>
        <Button label="Cancelar" class="p-button-text" @click="showContact = false" />
        <Button label="Guardar" :disabled="savingContact" @click="saveContact" />
      </template>
    </Dialog>

    <!-- Calificar (cierra la interacción) -->
    <Dialog v-model:visible="showDisposition" modal header="Calificar" :style="{ width: '460px' }">
      <div class="field">
        <label>Calificación</label>
        <Dropdown
          v-model="dispositionForm.idDispositionOption"
          :options="dispositionOptions"
          optionLabel="name"
          optionValue="id"
          placeholder="Elegí una opción"
          class="w-full"
          @change="onDispositionOptionChange"
        />
      </div>
      <div class="field">
        <label>Subcalificación</label>
        <InputText v-model="dispositionForm.subdispositionOption" class="w-full" />
      </div>
      <template v-if="selectedOption && selectedOption.form_fields && selectedOption.form_fields.length">
        <div v-for="ff in selectedOption.form_fields" :key="ff.id" class="field">
          <label>{{ ff.name }}<span v-if="ff.is_required"> *</span></label>
          <InputText v-model="formResponse[ff.name]" class="w-full" />
        </div>
      </template>
      <div class="field">
        <label>Comentarios</label>
        <Textarea v-model="dispositionForm.comments" rows="3" class="w-full" />
      </div>
      <template #footer>
        <Button label="Cancelar" class="p-button-text" @click="showDisposition = false" />
        <Button
          label="Calificar y cerrar"
          :disabled="dispositioning || !dispositionForm.idDispositionOption"
          @click="submitDisposition"
        />
      </template>
    </Dialog>
  </div>
</template>

<script>
import Editor from 'primevue/editor';
import 'quill/dist/quill.snow.css';
import EmailConversationService from '@/services/agent/email/conversation_service';
import { EmailConsumer } from '@/web_sockets/email_consumer';
import ConversationInfo from '@/components/agent/email/shared/ConversationInfo';

export default {
    name: 'AgentEmailIndex',
    components: { ConversationInfo, Editor },
    data () {
        return {
            email_color: '#52C159',
            activeTab: 0,
            inbox: { assigned: [], general: { new: [], waiting_client: [] } },
            active: null,
            isFullscreen: false,
            releasing: false,
            replyHtml: '',
            cc: '',
            bcc: '',
            showCc: false,
            attachmentNames: [],
            sending: false,
            quill: null,
            showEmoji: false,
            emojis: ['😀', '😁', '😂', '😊', '😍', '😉', '🙂', '👍', '🙏',
                '🎉', '✅', '❌', '⚠️', '📎', '📅', '📞', '✉️', '💡', '🔥', '👏'],
            // contact form
            showContact: false,
            savingContact: false,
            contactFields: [],
            contactData: {},
            // disposition form
            showDisposition: false,
            dispositioning: false,
            dispositionOptions: [],
            dispositionForm: { idDispositionOption: '', subdispositionOption: '', comments: '' },
            formResponse: {}
        };
    },
    computed: {
        visibleContactFields () {
            return (this.contactFields || []).filter((f) => !f.hide);
        },
        selectedOption () {
            return (this.dispositionOptions || []).find(
                (o) => o.id === this.dispositionForm.idDispositionOption
            );
        },
        replySubject () {
            const subject = (this.active && this.active.subject) || '';
            if (!subject) return 'Re:';
            return subject.toLowerCase().startsWith('re:') ? subject : `Re: ${subject}`;
        },
        // plain-text projection of the rich body — used both as the multipart
        // text/plain alternative and to decide whether there is content to send.
        replyPlain () {
            return (this.replyHtml || '')
                .replace(/<[^>]*>/g, ' ')
                .replace(/&nbsp;/g, ' ')
                .replace(/\s+/g, ' ')
                .trim();
        },
        hasBody () {
            return this.replyPlain.length > 0;
        }
    },
    created () {
        this.service = new EmailConversationService();
    },
    mounted () {
        this.loadInbox();
        try {
            EmailConsumer.getInstance({});
            window.document.addEventListener('email:email_new_conversation', this.onRealtime);
            window.document.addEventListener('email:email_new_message', this.onRealtime);
            window.document.addEventListener('email:email_conversation_attended', this.onRealtime);
        } catch (error) {
            // realtime is optional; the inbox still works via manual refresh
        }
        // the parent console (backdrop click) can ask us to return to the inbox
        window.document.addEventListener('email:request_close_thread', this.closeThread);
    },
    beforeUnmount () {
        window.document.removeEventListener('email:email_new_conversation', this.onRealtime);
        window.document.removeEventListener('email:email_new_message', this.onRealtime);
        window.document.removeEventListener('email:email_conversation_attended', this.onRealtime);
        window.document.removeEventListener('email:request_close_thread', this.closeThread);
        this.setParentReading(false);
    },
    methods: {
        fmtDate (value) {
            if (!value) return '';
            try {
                return new Date(value).toLocaleString();
            } catch (error) {
                return value;
            }
        },
        totalUnread () {
            const lists = [
                this.inbox.assigned,
                this.inbox.general.new,
                this.inbox.general.waiting_client
            ];
            return lists.reduce(
                (sum, list) => sum + list.reduce((s, c) => s + (c.unread || 0), 0),
                0
            );
        },
        // Mirror the WhatsApp bottom-bar bell: tell the parent console how many
        // unread emails exist so it can show the red bell + counter on the icon.
        syncToolbarBadge () {
            try {
                window.parent.document.dispatchEvent(
                    new CustomEvent('onEmailNewMessageEvent', {
                        detail: { count: this.totalUnread() }
                    })
                );
            } catch (error) {
                // parent unreachable (e.g. standalone dev) — ignore
            }
        },
        // Promote/restore the iframe wrapper to a large centered reading modal.
        setParentReading (reading) {
            try {
                window.parent.document.dispatchEvent(
                    new CustomEvent('onEmailReadingEvent', { detail: { reading } })
                );
            } catch (error) {
                // standalone dev — ignore
            }
        },
        setParentFullscreen (fullscreen) {
            try {
                window.parent.document.dispatchEvent(
                    new CustomEvent('onEmailFullscreenEvent', { detail: { fullscreen } })
                );
            } catch (error) {
                // standalone dev — ignore
            }
        },
        toggleFullscreen () {
            this.isFullscreen = !this.isFullscreen;
            this.setParentFullscreen(this.isFullscreen);
        },
        onEditorLoad (event) {
            this.quill = event && event.instance ? event.instance : null;
        },
        insertEmoji (emoji) {
            if (this.quill) {
                const range = this.quill.getSelection(true);
                const index = range ? range.index : this.quill.getLength();
                this.quill.insertText(index, emoji);
                this.quill.setSelection(index + emoji.length);
            } else {
                this.replyHtml = `${this.replyHtml || ''}${emoji}`;
            }
            this.showEmoji = false;
        },
        async releaseConversation () {
            if (this.releasing) return;
            this.releasing = true;
            const ok = await this.service.release(this.active.id);
            this.releasing = false;
            if (ok) {
                this.$toast.add({
                    severity: 'success',
                    summary: 'Desasignado',
                    detail: 'El correo volvió a la cola como nuevo.',
                    life: 3000
                });
                this.closeThread();
            }
        },
        resetComposer () {
            this.replyHtml = '';
            this.cc = '';
            this.bcc = '';
            this.showCc = false;
            this.attachmentNames = [];
            if (this.$refs.files) this.$refs.files.value = '';
        },
        async loadInbox () {
            const data = await this.service.getInbox();
            if (data && data.general) this.inbox = data;
            this.syncToolbarBadge();
        },
        async open (id) {
            const data = await this.service.getConversationDetail(id);
            if (data && data.id) {
                this.active = data;
                this.setParentReading(true);
                await this.service.markAsRead(id);
                this.syncToolbarBadge();
            }
        },
        closeThread () {
            this.active = null;
            this.isFullscreen = false;
            this.showEmoji = false;
            this.resetComposer();
            this.setParentReading(false);
            this.loadInbox();
        },
        closePanel () {
            this.setParentReading(false);
            try {
                window.parent.document.dispatchEvent(new CustomEvent('onEmailCloseContainerEvent'));
            } catch (error) {
                // standalone dev — ignore
            }
        },
        async attend (id) {
            const data = await this.service.attend(id);
            if (data && data.id) {
                this.active = data;
                this.setParentReading(true);
            }
            this.loadInbox();
        },
        onFilesChange () {
            const files = this.$refs.files && this.$refs.files.files;
            this.attachmentNames = files ? Array.from(files).map((f) => f.name) : [];
        },
        async reply (mode) {
            if (!this.hasBody || this.sending) return;
            this.sending = true;
            const formData = new FormData();
            formData.append('body_html', this.replyHtml);
            formData.append('body_text', this.replyPlain);
            formData.append('mode', mode);
            if (this.cc) formData.append('cc', this.cc);
            if (this.bcc) formData.append('bcc', this.bcc);
            const files = this.$refs.files && this.$refs.files.files;
            if (files) {
                for (let i = 0; i < files.length; i++) {
                    formData.append('attachments', files[i]);
                }
            }
            const data = await this.service.reply(this.active.id, formData);
            this.sending = false;
            if (!data || data.detail) {
                this.$toast.add({
                    severity: 'error',
                    summary: 'Error',
                    detail: (data && data.detail) || 'No se pudo enviar el correo.',
                    life: 5000
                });
                return;
            }
            this.resetComposer();
            if (mode === 'unassign') {
                this.closeThread();
            } else {
                this.active = data;
                if (mode === 'dispose') this.openDisposition();
            }
        },
        async onRealtime (event) {
            const type = event && event.type ? event.type : '';
            const detail = (event && event.detail) || {};
            await this.loadInbox();
            const convId = detail.conversation_id || detail.conversationId;
            if (this.active && convId && Number(convId) === Number(this.active.id)) {
                const data = await this.service.getConversationDetail(this.active.id);
                if (data && data.id) {
                    this.active = data;
                    this.service.markAsRead(this.active.id);
                }
            } else if (type.indexOf('attended') === -1) {
                const who = detail.client_name || detail.client_mail || detail.from || '';
                this.$toast.add({
                    severity: 'info',
                    summary: 'Nuevo correo',
                    detail: who ? `Nuevo correo de ${who}` : 'Llegó un nuevo correo',
                    life: 4000
                });
            }
        },
        // --- Guardar contacto ---
        async openContactForm () {
            this.contactFields = await this.service.getContactFields(this.active.id);
            const data = {};
            (this.contactFields || []).forEach((f) => {
                data[f.name] = /mail|email|correo/i.test(f.name)
                    ? (this.active.client_mail || '')
                    : '';
            });
            this.contactData = data;
            this.showContact = true;
        },
        async saveContact () {
            this.savingContact = true;
            const data = await this.service.createContact(this.active.id, this.contactData);
            this.savingContact = false;
            if (data && data.id) {
                this.active = data;
                this.showContact = false;
            }
        },
        // --- Calificar ---
        async openDisposition () {
            // Open the disposition pop-up directly. If the conversation has no
            // contact, the backend auto-creates a minimal one from the sender's
            // email on submit (email contacts are identified by address).
            this.dispositionOptions = await this.service.getDispositionOptions(this.active.id);
            this.dispositionForm = { idDispositionOption: '', subdispositionOption: '', comments: '' };
            this.formResponse = {};
            this.showDisposition = true;
        },
        // Reset the management-form answers when the option changes so stale
        // keys from a previously selected option don't leak into the payload
        // (the backend rejects keys that don't belong to the new form).
        onDispositionOptionChange () {
            const fields = (this.selectedOption && this.selectedOption.form_fields) || [];
            const response = {};
            fields.forEach((f) => { response[f.name] = ''; });
            this.formResponse = response;
        },
        async submitDisposition () {
            const fields = (this.selectedOption && this.selectedOption.form_fields) || [];
            // client-side guard: required management-form fields must be filled
            const missing = fields.filter(
                (f) => f.is_required && !String(this.formResponse[f.name] || '').trim()
            );
            if (missing.length) {
                this.$toast.add({
                    severity: 'warn',
                    summary: 'Formulario de gestión',
                    detail: `Completá los campos obligatorios: ${missing.map((f) => f.name).join(', ')}`,
                    life: 5000
                });
                return;
            }
            this.dispositioning = true;
            const payload = {
                idDispositionOption: this.dispositionForm.idDispositionOption,
                subdispositionOption: this.dispositionForm.subdispositionOption || '',
                comments: this.dispositionForm.comments || ''
            };
            if (fields.length) {
                payload.respuestaFormularioGestion = this.formResponse;
            }
            const res = await this.service.disposition(this.active.id, payload);
            this.dispositioning = false;
            if (res && res.ok) {
                this.showDisposition = false;
                this.closeThread();
            } else {
                const body = (res && res.body) || {};
                const detail = body.detail || body.Error ||
                    (typeof body === 'object'
                        ? Object.values(body).flat().join(' ')
                        : '') ||
                    'No se pudo calificar la conversación.';
                this.$toast.add({
                    severity: 'error', summary: 'No se pudo calificar', detail, life: 6000
                });
            }
        }
    }
};
</script>

<style scoped>
.email-agent-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  font-size: 13px;
  background: #fff;
}
/* Header uses the default Toolbar treatment, like the other channels */
.spacer {
  flex: 1;
}

/* Inbox list (Thunderbird-style) */
.inbox-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.list {
  overflow-y: auto;
  height: calc(100% - 4px);
}
.email-agent-panel :deep(.p-tabview-panels) {
  padding: 0;
}
.email-agent-panel :deep(.p-tabview-nav) {
  font-size: 0.82rem;
}
.empty {
  text-align: center;
  color: #9aa0a6;
  padding: 24px 8px;
}

/* Thread (reading) */
.email-thread {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.thread-head {
  padding: 10px 14px;
  border-bottom: 1px solid #e5e7eb;
}
.thread-title {
  font-size: 1.05rem;
  font-weight: 700;
  color: #2b2f33;
}
.thread-sub {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 4px;
  font-size: 0.8rem;
  color: #6b7280;
  flex-wrap: wrap;
}
.thread-sub .head-actions {
  margin-left: auto;
  display: flex;
  gap: 4px;
}
.msgs {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  background: #fafbfc;
}
.msg-line {
  display: flex;
  margin-bottom: 12px;
}
.msg-line.out {
  justify-content: flex-end;
}
.bubble {
  max-width: 78%;
  border: 1px solid #e7e9ec;
  border-radius: 10px;
  padding: 10px 12px;
}
.bubble-in {
  background: #f4f5f7;
}
.bubble-out {
  background: #eef6ee;
}
.bubble-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}
.bubble-from {
  font-weight: 600;
  color: #3b4046;
  font-size: 0.82rem;
}
.bubble-date {
  font-size: 0.72rem;
  color: #9aa0a6;
}
.bubble-body {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  color: #2b2f33;
}
.bubble-body :deep(img) {
  max-width: 100%;
  height: auto;
}
.bubble-attachments {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.attachment {
  text-decoration: none;
  color: #4a6da7;
  font-size: 0.8rem;
}

/* Composer */
.composer {
  border-top: 1px solid #e5e7eb;
  padding: 10px 14px;
  background: #fff;
}
.composer-fields .cfield {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.composer-fields label {
  width: 56px;
  font-size: 0.75rem;
  color: #6b7280;
  text-align: right;
}
.composer-fields :deep(.p-inputtext) {
  font-size: 0.82rem;
  padding: 4px 8px;
}
.body-box {
  margin: 6px 0;
  font-size: 0.86rem;
}
.hidden-file {
  display: none;
}
.composer-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.attach-names {
  font-size: 0.75rem;
  color: #6b7280;
}
.emoji-wrap {
  position: relative;
}
.emoji-palette {
  position: absolute;
  bottom: 100%;
  left: 0;
  margin-bottom: 6px;
  z-index: 10;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
  padding: 6px;
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 2px;
  width: 200px;
}
.emoji-item {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 1.15rem;
  line-height: 1.6;
  border-radius: 6px;
}
.emoji-item:hover {
  background: #f1f3f5;
}
.send-group {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.field {
  margin-bottom: 12px;
}
.field label {
  display: block;
  margin-bottom: 4px;
  font-weight: 600;
  font-size: 0.8rem;
}
</style>
