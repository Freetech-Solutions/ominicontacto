<template>
  <div>
    <Fieldset legend="Detalle de conversación Instagram" :toggleable="true">
      <div class="grid">
        <div class="sm:col-12 md:col-12 lg:col-6 xl:col-6">
          <span>
            <b>{{ $t("models.whatsapp.conversation.campaign") }}:</b>
            {{ agtInstagramConversationInfo.campaignName }}
          </span>
        </div>
        <div class="sm:col-12 md:col-12 lg:col-6 xl:col-6">
          <span>
            <b>Instagram User ID:</b>
            <Tag icon="pi pi-id-card" severity="info" :value="agtInstagramConversationInfo.page_client_id" rounded></Tag>
          </span>
        </div>
        <div class="sm:col-12 md:col-12 lg:col-6 xl:col-6">
          <span>
            <b>Cuenta Instagram:</b>
            {{ agtInstagramConversationInfo.page.name }} ({{ agtInstagramConversationInfo.page.page_id }})
          </span>
        </div>
        <div class="sm:col-12 md:col-12 lg:col-6 xl:col-6">
          <span>
            <b>{{ $t("models.whatsapp.conversation.message") }}:</b>
            <Tag icon="pi pi-comments" severity="primary" :value="agtInstagramConversationInfo.messageNumber" rounded></Tag>
          </span>
        </div>
        <div class="sm:col-12 md:col-12 lg:col-6 xl:col-6">
          <span>
            <b>{{ $t("models.whatsapp.conversation.expire") }}:</b>
            <Tag :icon="getIcon(agtInstagramConversationInfo.expire)" :severity="getColor(agtInstagramConversationInfo.expire)" :value="getValue(agtInstagramConversationInfo.expire)" rounded></Tag>
          </span>
        </div>
        <div class="sm:col-12 md:col-12 lg:col-6 xl:col-6">
          <span>
            <b>{{ $t("models.whatsapp.conversation.is_active") }}:</b>
            <i v-if="agtInstagramConversationInfo.isActive" class="pi pi-check-circle" style="color: green"></i>
            <i v-else class="pi pi-times-circle" style="color: red"></i>
          </span>
        </div>
      </div>
    </Fieldset>
    <HeaderConversation :isExpired="isExpired" :viewAsReport="true" class="mt-4" />
    <div class="flex justify-content-between flex-wrap my-2">
      <div class="flex align-items-center justify-content-center">
        <Tag v-if="isExpired" icon="pi pi-clock" :value="`${$t('views.whatsapp.conversations.expired_conversation')}`" severity="warning" rounded></Tag>
      </div>
      <div class="flex align-items-center justify-content-center">
        <Tag :style="{ background: instagramColor }" icon="pi pi-sitemap" :value="`${$t('globals.campaign')} (${agtInstagramConversationInfo.campaignName})`" severity="info" rounded></Tag>
      </div>
    </div>
    <ListMessages id="listMessages" class="scroll" />
  </div>
</template>

<script>
import { mapState } from 'vuex';
import HeaderConversation from '@/components/agent/instagram/conversation/HeaderConversation';
import ListMessages from '@/components/agent/instagram/conversation/ListMessages';
import { COLORS } from '@/globals';

export default {
    inject: ['$helpers'],
    components: {
        HeaderConversation,
        ListMessages
    },
    data () {
        return {
            instagramColor: COLORS.INSTAGRAM.Pink,
            isExpired: false
        };
    },
    computed: {
        ...mapState(['agtInstagramConversationInfo'])
    },
    methods: {
        checkExpirationDate () {
            if (this.agtInstagramConversationInfo.expire) {
                const now = new Date();
                const expire = new Date(this.agtInstagramConversationInfo.expire);
                this.isExpired = now > expire;
            }
        },
        getColor (expired) {
            const currentDate = new Date();
            const expiredDate = new Date(expired);
            if (expiredDate.getTime() < currentDate.getTime()) {
                return 'warning';
            } else if (expiredDate.getTime() > currentDate.getTime()) {
                return 'success';
            }
            return 'secondary';
        },
        getValue (expired) {
            return this.$helpers.getDatetimeFormat(expired);
        },
        getIcon (expired) {
            const currentDate = new Date();
            const expiredDate = new Date(expired);
            if (expiredDate.getTime() < currentDate.getTime()) {
                return 'pi pi-exclamation-triangle';
            } else if (expiredDate.getTime() > currentDate.getTime()) {
                return 'pi pi-check-circle';
            }
            return 'pi pi-clock';
        }
    },
    watch: {
        agtInstagramConversationInfo: {
            handler () {
                this.checkExpirationDate();
            },
            deep: true,
            immediate: true
        }
    }
};
</script>

<style scoped>
.scroll {
  overflow-y: scroll;
  height: calc(100vh - 180px);
}
</style>
