<template>
  <div class="last-conversation-wrapper">
    <section class="last-conversation-info">
      <div class="last-conversation-info__top">
        <div class="last-conversation-info__identity">
          <div class="last-conversation-info__phone">
            {{ phoneLabel }}
          </div>

          <div class="last-conversation-info__headline">
            <div class="last-conversation-info__title-row">
              <h2 class="last-conversation-info__title">
                {{ contactLabel }}
              </h2>

              <span class="last-conversation-info__message-count">
                {{ messageCount }} {{ $t('globals.messages') }}
              </span>
            </div>

            <div
              v-if="summaryText"
              class="last-conversation-info__summary"
            >
              {{ summaryText }}
            </div>
          </div>
        </div>

        <button
          type="button"
          class="last-conversation-info__toggle"
          @click="isInfoCollapsed = !isInfoCollapsed"
        >
          <i
            class="pi"
            :class="isInfoCollapsed ? 'pi-chevron-down' : 'pi-chevron-up'"
          />
        </button>
      </div>

      <transition name="conversation-info-collapse">
        <div
          v-show="!isInfoCollapsed"
          class="last-conversation-info__details"
        >
          <div class="last-conversation-info__grid">
            <div class="last-conversation-info__item">
              <span class="last-conversation-info__label">ID</span>
              <span class="last-conversation-info__value">
                {{ conversationIdLabel }}
              </span>
            </div>

            <div class="last-conversation-info__item">
              <span class="last-conversation-info__label">
                {{ $t('globals.agent') }}
              </span>
              <span class="last-conversation-info__value">
                {{ agentLabel }}
              </span>
            </div>

            <div class="last-conversation-info__item">
              <span class="last-conversation-info__label">
                {{ $t('globals.disposition') }}
              </span>
              <span class="last-conversation-info__value">
                {{ dispositionLabel }}
              </span>
            </div>

            <div class="last-conversation-info__item">
              <span class="last-conversation-info__label">
                {{ $t('globals.was_closed_by_system') }}
              </span>
              <span class="last-conversation-info__value">
                {{ wasClosedBySystemLabel }}
              </span>
            </div>

            <div class="last-conversation-info__item last-conversation-info__item--full">
              <span class="last-conversation-info__label">
                {{ $t('globals.campaign') }}
              </span>
              <span class="last-conversation-info__value">
                {{ campaignLabel }}
              </span>
            </div>

            <div class="last-conversation-info__item">
              <span class="last-conversation-info__label">
                {{ $t('globals.line') }}
              </span>
              <span class="last-conversation-info__value">
                {{ lineLabel }}
              </span>
            </div>

            <div class="last-conversation-info__item">
              <span class="last-conversation-info__label">
                {{ $t('globals.date') }}
              </span>
              <span class="last-conversation-info__value">
                {{ timestampLabel }}
              </span>
            </div>
          </div>
        </div>
      </transition>
    </section>

    <div
      ref="scrollContainer"
      class="last-conversation-messages"
      @scroll="onScroll"
    >
      <div
        v-if="hasMessages"
        class="last-conversation-messages__list"
      >
        <div
          v-for="message in agtWhatsLastCoversationMessages"
          :key="message.id"
          class="last-conversation-messages__item"
          :class="message.itsMine
            ? 'last-conversation-messages__item--mine'
            : 'last-conversation-messages__item--their'"
        >
          <div
            v-if="!message.itsMine && message.from"
            class="last-conversation-messages__sender"
          >
            {{ message.from }}
          </div>

          <Message
            :message="message"
            variant="history"
          />
        </div>
      </div>

      <div v-else class="last-conversation-empty">
        <i class="pi pi-comments last-conversation-empty__icon" />
        <div class="last-conversation-empty__title">
          {{ $t('globals.no_results') }}
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { mapState } from 'vuex';
import Message from '@/components/agent/whatsapp/conversation/Message';

const getContactName = (client = {}, fallback = '-') => {
    const clientData = client && client.data ? client.data : {};
    return (
        clientData.nombre ||
        clientData.name ||
        clientData.Nombre ||
        clientData.Name ||
        fallback
    );
};

export default {
    name: 'LastConversationMessages',
    components: {
        Message
    },
    data () {
        return {
            autoScroll: true,
            isInfoCollapsed: true
        };
    },
    computed: {
        ...mapState([
            'agtWhatsLastCoversationMessages',
            'agtWhatsLastCoversationInfo'
        ]),
        conversationInfo () {
            return this.agtWhatsLastCoversationInfo || {};
        },
        hasMessages () {
            return (
                Array.isArray(this.agtWhatsLastCoversationMessages) &&
                this.agtWhatsLastCoversationMessages.length > 0
            );
        },
        phoneLabel () {
            const client = this.conversationInfo.client || {};
            return client.phone || this.conversationInfo.destination || '-';
        },
        contactLabel () {
            return getContactName(
                this.conversationInfo.client,
                this.conversationInfo.client_alias || this.phoneLabel
            );
        },
        conversationIdLabel () {
            return this.conversationInfo.id || '-';
        },
        agentLabel () {
            return this.conversationInfo.agent || '-';
        },
        dispositionLabel () {
            const disposition = this.conversationInfo.disposition || {};
            return disposition.name || '-';
        },
        campaignLabel () {
            return this.conversationInfo.campaignName || '-';
        },
        lineLabel () {
            const line = this.conversationInfo.line || {};
            return line.name || '-';
        },
        timestampLabel () {
            return this.formatDate(this.conversationInfo.timestamp);
        },
        wasClosedBySystemLabel () {
            return this.conversationInfo.wasClosedBySystem
                ? this.$t('globals.yes')
                : this.$t('globals.no');
        },
        messageCount () {
            if (typeof this.conversationInfo.messageNumber === 'number') {
                return this.conversationInfo.messageNumber;
            }
            return this.agtWhatsLastCoversationMessages.length;
        },
        summaryText () {
            return [
                `ID ${this.conversationIdLabel}`,
                this.agentLabel,
                this.dispositionLabel !== '-' ? this.dispositionLabel : null,
                this.timestampLabel !== '-' ? this.timestampLabel : null
            ]
                .filter(Boolean)
                .join(' · ');
        }
    },
    methods: {
        onScroll ({ target: { scrollTop, clientHeight, scrollHeight } }) {
            this.autoScroll = scrollTop + clientHeight >= scrollHeight - 200;
        },
        scrollToBottom () {
            if (!this.$refs.scrollContainer) return;

            this.$nextTick(() => {
                this.$refs.scrollContainer.scrollTo({
                    top: this.$refs.scrollContainer.scrollHeight,
                    behavior: 'smooth'
                });
            });
        },
        formatDate (value) {
            if (!value) return '-';

            const date = new Date(value);

            if (Number.isNaN(date.getTime())) return '-';

            return date.toLocaleString('es-AR', {
                day: '2-digit',
                month: 'short',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        }
    },
    watch: {
        agtWhatsLastCoversationMessages: {
            handler (newMsgs) {
                if (!newMsgs || !newMsgs.length) return;

                if (this.autoScroll && this.$refs.scrollContainer) {
                    this.scrollToBottom();
                }
            },
            deep: true
        }
    }
};
</script>

<style scoped>
.last-conversation-wrapper {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background:
        radial-gradient(circle at top right, rgba(59, 130, 246, 0.10), transparent 24%),
        linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
    border: 1px solid #dbe5f0;
    border-radius: 18px;
    overflow: hidden;
    box-shadow: 0 14px 36px rgba(15, 23, 42, 0.08);
}

.last-conversation-info {
    padding: 0.95rem 1rem 0.9rem;
    background: linear-gradient(135deg, #ffffff 0%, #f7fbff 50%, #eef8f1 100%);
    border-bottom: 1px solid #dbe5f0;
}

.last-conversation-info__top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.85rem;
}

.last-conversation-info__identity {
    display: flex;
    gap: 0.8rem;
    min-width: 0;
    flex: 1;
}

.last-conversation-info__phone {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.38rem 0.7rem;
    border-radius: 999px;
    background: #0f172a;
    color: #f8fafc;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    white-space: nowrap;
}

.last-conversation-info__headline {
    min-width: 0;
    flex: 1;
}

.last-conversation-info__title-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    justify-content: space-between;
}

.last-conversation-info__title {
    margin: 0;
    font-size: 1rem;
    line-height: 1.2;
    font-weight: 700;
    color: #0f172a;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.last-conversation-info__message-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.3rem 0.65rem;
    border-radius: 999px;
    background: #ecfdf3;
    color: #166534;
    border: 1px solid #ccefdc;
    font-size: 0.72rem;
    font-weight: 700;
    white-space: nowrap;
}

.last-conversation-info__summary {
    margin-top: 0.32rem;
    color: #475569;
    font-size: 0.76rem;
    line-height: 1.45;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.last-conversation-info__toggle {
    width: 32px;
    height: 32px;
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 999px;
    border: 1px solid #d5e1ec;
    background: rgba(255, 255, 255, 0.92);
    color: #334155;
    cursor: pointer;
    transition: all 0.2s ease;
}

.last-conversation-info__toggle:hover {
    background: #f8fafc;
    border-color: #c2d2e3;
}

.last-conversation-info__details {
    margin-top: 0.85rem;
}

.last-conversation-info__grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.55rem;
}

.last-conversation-info__item {
    display: flex;
    flex-direction: column;
    gap: 0.22rem;
    padding: 0.72rem 0.78rem;
    background: rgba(255, 255, 255, 0.78);
    border: 1px solid #dce7f3;
    border-radius: 12px;
}

.last-conversation-info__item--full {
    grid-column: 1 / -1;
}

.last-conversation-info__label {
    color: #64748b;
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.last-conversation-info__value {
    color: #0f172a;
    font-size: 0.88rem;
    font-weight: 700;
    word-break: break-word;
}

.last-conversation-messages {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 1rem;
    background:
        radial-gradient(circle at top left, rgba(37, 211, 102, 0.08), transparent 18%),
        linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
}

.last-conversation-messages__list {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
}

.last-conversation-messages__item {
    display: flex;
    flex-direction: column;
    gap: 0.32rem;
}

.last-conversation-messages__item--mine {
    align-items: flex-end;
}

.last-conversation-messages__item--their {
    align-items: flex-start;
}

.last-conversation-messages__sender {
    padding: 0 0.3rem;
    color: #475569;
    font-size: 0.74rem;
    font-weight: 700;
}

.last-conversation-empty {
    min-height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    color: #64748b;
    text-align: center;
}

.last-conversation-empty__icon {
    font-size: 1.6rem;
    color: #94a3b8;
}

.last-conversation-empty__title {
    font-size: 0.92rem;
    font-weight: 600;
}

.conversation-info-collapse-enter-active,
.conversation-info-collapse-leave-active {
    transition: all 0.22s ease;
}

.conversation-info-collapse-enter-from,
.conversation-info-collapse-leave-to {
    opacity: 0;
    max-height: 0;
    transform: translateY(-8px);
}

:deep(.message-r),
:deep(.message-l) {
    float: none;
}

:deep(.wa-message-card) {
    margin: 0;
}

@media (max-width: 768px) {
    .last-conversation-info {
        padding: 0.8rem;
    }

    .last-conversation-info__identity {
        flex-direction: column;
        gap: 0.55rem;
    }

    .last-conversation-info__title-row {
        align-items: flex-start;
        flex-direction: column;
        gap: 0.45rem;
    }

    .last-conversation-info__summary {
        white-space: normal;
    }

    .last-conversation-info__grid {
        grid-template-columns: 1fr;
    }

    .last-conversation-messages {
        padding: 0.8rem;
    }
}
</style>
