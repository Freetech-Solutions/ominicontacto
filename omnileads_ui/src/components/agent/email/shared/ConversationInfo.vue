<template>
  <div
    class="email-row"
    :class="{ unread: conversation.unread > 0 }"
    @click="onRowClick"
  >
    <div class="row-top">
      <i class="dir" :class="directionIcon" v-tooltip.top="directionLabel"></i>
      <span class="sender">{{ conversation.client_name || conversation.client_mail }}</span>
      <span class="spacer"></span>
      <span v-if="conversation.unread > 0" class="unread-count">{{ conversation.unread }}</span>
      <span class="date">{{ date }}</span>
    </div>

    <div class="subject">{{ conversation.subject || '(sin asunto)' }}</div>

    <div class="row-meta">
      <span class="status" :class="`st-${conversation.status}`">{{ statusLabel }}</span>
      <span class="dot">·</span>
      <span class="campaign"><i class="pi pi-sitemap"></i> {{ conversation.campaign_name || '-----' }}</span>
      <span class="dot">·</span>
      <span class="count">{{ conversation.messages }} msg</span>
      <span class="spacer"></span>
      <Button
        v-if="context === 'general'"
        label="Tomar"
        icon="pi pi-inbox"
        class="p-button-text p-button-sm take-btn"
        @click.stop="$emit('take', conversation.id)"
      />
    </div>
  </div>
</template>

<script>
const STATUS_LABELS = {
    new: 'Nuevo',
    reopened: 'Reabierto',
    assigned: 'Asignado',
    in_progress: 'En gestión',
    answered: 'Respondido',
    closed: 'Cerrado'
};

export default {
    name: 'EmailConversationInfo',
    props: {
        conversation: {
            type: Object,
            default: () => ({
                id: null,
                subject: '',
                client_mail: '',
                client_name: '',
                campaign_name: '',
                status: 'new',
                messages: 0,
                unread: 0,
                date_last_interaction: null
            })
        },
        context: {
            type: String,
            default: 'general' // 'assigned' | 'general'
        }
    },
    emits: ['open', 'take'],
    methods: {
        // A conversation in the general inbox can only be read by TAKING it
        // (which assigns it). Only an already-assigned conversation opens
        // directly into the thread.
        onRowClick () {
            this.$emit(this.context === 'assigned' ? 'open' : 'take', this.conversation.id);
        }
    },
    computed: {
        date () {
            const value = this.conversation.date_last_interaction || this.conversation.timestamp;
            if (!value) return '';
            try {
                return new Date(value).toLocaleString();
            } catch (error) {
                return value;
            }
        },
        statusLabel () {
            return STATUS_LABELS[this.conversation.status] || this.conversation.status;
        },
        // OUT when we already answered (waiting on the client), IN otherwise.
        directionIcon () {
            return this.conversation.status === 'answered'
                ? 'pi pi-arrow-up-right'
                : 'pi pi-arrow-down-left';
        },
        directionLabel () {
            return this.conversation.status === 'answered' ? 'Saliente' : 'Entrante';
        }
    }
};
</script>

<style scoped>
.email-row {
  padding: 7px 10px;
  border-bottom: 1px solid #eceef0;
  border-left: 3px solid transparent;
  cursor: pointer;
  line-height: 1.35;
}
.email-row:hover {
  background: #f7f8f9;
}
.email-row.unread {
  border-left-color: #6fbf73;
  background: #fbfdfb;
}
.row-top {
  display: flex;
  align-items: center;
  gap: 6px;
}
.dir {
  font-size: 0.75rem;
  color: #9aa0a6;
}
.sender {
  font-size: 0.86rem;
  color: #2b2f33;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.email-row.unread .sender {
  font-weight: 700;
}
.spacer {
  flex: 1;
}
.unread-count {
  background: #6fbf73;
  color: #fff;
  font-size: 0.65rem;
  border-radius: 9px;
  padding: 0 6px;
  line-height: 16px;
}
.date {
  font-size: 0.72rem;
  color: #9aa0a6;
  white-space: nowrap;
}
.subject {
  font-size: 0.82rem;
  color: #4b5258;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin: 1px 0;
}
.email-row.unread .subject {
  color: #2b2f33;
  font-weight: 600;
}
.row-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.7rem;
  color: #9aa0a6;
}
.row-meta .status {
  font-weight: 600;
}
.row-meta .campaign .pi {
  font-size: 0.65rem;
}
.row-meta .dot {
  color: #cbd0d4;
}
/* subtle, low-saturation status accents */
.st-new, .st-reopened { color: #4f8a52; }
.st-assigned, .st-in_progress { color: #5b6bb0; }
.st-answered { color: #7a6aa8; }
.st-closed { color: #9aa0a6; }
.take-btn {
  padding: 2px 8px !important;
  font-size: 0.72rem !important;
}
</style>
