<template>
  <div class="last-conversation-wrapper">
    <div
      class="last-conversation-info"
      :class="{ 'last-conversation-info--collapsed': isInfoCollapsed }"
    >
      <div class="last-conversation-info__top">
        <div class="last-conversation-info__left">
          <div class="last-conversation-info__phone">
            {{ agtWhatsLastCoversationInfo.client?.phone || '-' }}
          </div>

          <div
            v-if="isInfoCollapsed"
            class="last-conversation-info__summary"
          >
            <span>ID {{ agtWhatsLastCoversationInfo.id || '-' }}</span>
            <span>·</span>
            <span>{{ agtWhatsLastCoversationInfo.agent || '-' }}</span>
            <span>·</span>
            <span>{{ agtWhatsLastCoversationInfo.disposition?.name || '-' }}</span>
            <span>·</span>
            <span>{{ formatDate(agtWhatsLastCoversationInfo.timestamp) }}</span>
          </div>
        </div>

        <div class="last-conversation-info__top-actions">
          <span class="last-conversation-info__badge">
            {{ agtWhatsLastCoversationInfo.messageNumber ?? '-' }}
          </span>

          <button
            type="button"
            class="last-conversation-info__toggle"
            @click="isInfoCollapsed = !isInfoCollapsed"
          >
            {{ isInfoCollapsed ? '▼' : '▲' }}
          </button>
        </div>
      </div>

      <transition name="conversation-info-collapse">
        <div v-show="!isInfoCollapsed" class="last-conversation-info__content">
          <div class="last-conversation-info__grid">
            <div class="last-conversation-info__item">
              <span class="last-conversation-info__label">ID</span>
              <span class="last-conversation-info__value">
                {{ agtWhatsLastCoversationInfo.id || '-' }}
              </span>
            </div>

            <div class="last-conversation-info__item">
              <span class="last-conversation-info__label">
                {{ $t('globals.agent') }}
              </span>
              <span class="last-conversation-info__value">
                {{ agtWhatsLastCoversationInfo.agent || '-' }}
              </span>
            </div>

            <div class="last-conversation-info__item">
              <span class="last-conversation-info__label">
                {{ $t('globals.was_closed_by_system') }}
              </span>
              <span class="last-conversation-info__value">
                {{ agtWhatsLastCoversationInfo.wasClosedBySystem ? $t('globals.yes') : $t('globals.no') }}
              </span>
            </div>

            <div class="last-conversation-info__item">
              <span class="last-conversation-info__label">
                {{ $t('globals.disposition') }}
              </span>
              <span class="last-conversation-info__value">
                {{ agtWhatsLastCoversationInfo.disposition?.name || '-' }}
              </span>
            </div>

            <div class="last-conversation-info__item last-conversation-info__item--full">
              <span class="last-conversation-info__label">
                {{ $t('globals.campaign') }}
              </span>
              <span class="last-conversation-info__value">
                {{ agtWhatsLastCoversationInfo.campaignName || '-' }}
              </span>
            </div>

            <div class="last-conversation-info__item last-conversation-info__item--full">
              <span class="last-conversation-info__label">
                {{ $t('globals.line') }}
              </span>
              <span class="last-conversation-info__value">
                {{ agtWhatsLastCoversationInfo.line?.name || '-' }}
              </span>
            </div>

            <div class="last-conversation-info__item last-conversation-info__item--full">
              <span class="last-conversation-info__label">
                {{ $t('globals.date') }}
              </span>
              <span class="last-conversation-info__value">
                {{ formatDate(agtWhatsLastCoversationInfo.timestamp) }}
              </span>
            </div>
          </div>
        </div>
      </transition>
    </div>

    <div
      class="last-conversation-messages"
      @scroll="onScroll"
      ref="scrollContainer"
    >
      <div
        v-if="agtWhatsLastCoversationMessages && agtWhatsLastCoversationMessages.length"
        class="last-conversation-messages__list"
      >
        <div
          v-for="message in agtWhatsLastCoversationMessages"
          :key="message.id"
          class="last-conversation-messages__item"
        >
          <Message :message="message" />
        </div>
      </div>

      <div v-else class="last-conversation-empty">
        {{ $t('globals.no_results') }}
      </div>
    </div>
  </div>
</template>

<script>
import { mapState } from 'vuex';
import Message from '@/components/agent/whatsapp/conversation/Message';

export default {
    name: 'LastConversationMessages',
    components: {
        Message
    },
    data () {
        return {
            autoScroll: true,
            isInfoCollapsed: false
        };
    },
    computed: {
        ...mapState([
            'agtWhatsLastCoversationMessages',
            'agtWhatsLastCoversationInfo'
        ])
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

            return date.toLocaleString('es-ES', {
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
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
}

.last-conversation-info {
    padding: 0.45rem 0.55rem;
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    border-bottom: 1px solid #e5e7eb;
}

.last-conversation-info__top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.4rem;
}

.last-conversation-info__left {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
}

.last-conversation-info__phone {
    padding: 0.18rem 0.45rem;
    background: #f1f5f9;
    border: 1px solid #dbe3ee;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 700;
}

.last-conversation-info__summary {
    display: flex;
    gap: 0.35rem;
    font-size: 0.75rem;
    color: #475569;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.last-conversation-info__top-actions {
    display: flex;
    align-items: center;
    gap: 0.35rem;
}

.last-conversation-info__badge {
    padding: 0.18rem 0.45rem;
    background: #ecfdf3;
    border: 1px solid #ccefdc;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 700;
}

.last-conversation-info__toggle {
    width: 22px;
    height: 22px;
    border-radius: 999px;
    border: 1px solid #dbe3ee;
    background: #fff;
    cursor: pointer;
}

.last-conversation-info__content {
    margin-top: 0.4rem;
}

.last-conversation-info__grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.25rem;
}

.last-conversation-info__item {
    display: flex;
    justify-content: space-between;
    padding: 0.28rem 0.4rem;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
}

.last-conversation-info__item--full {
    grid-column: 1 / -1;
}

.last-conversation-info__label {
    font-size: 0.6rem;
    color: #64748b;
}

.last-conversation-info__value {
    font-size: 0.78rem;
    font-weight: 700;
}

.last-conversation-messages {
    flex: 1;
    overflow-y: auto;
    padding: 0.6rem;
    background: #f8fafc;
}

.last-conversation-messages__list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.last-conversation-empty {
    text-align: center;
    padding: 1rem;
    color: #64748b;
}

.conversation-info-collapse-enter-active,
.conversation-info-collapse-leave-active {
    transition: all 0.2s ease;
}

.conversation-info-collapse-enter-from,
.conversation-info-collapse-leave-to {
    opacity: 0;
    max-height: 0;
}
</style>