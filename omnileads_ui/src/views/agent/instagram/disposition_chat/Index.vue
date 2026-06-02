<template>
  <div>
    <Header @handleCloseEvent="closeEvent" />
    <Tab ref="tabRef" />
  </div>
</template>

<script>
import Header from '@/components/agent/instagram/disposition_chat/Header';
import Tab from '@/components/agent/instagram/disposition_chat/Tab';
import { mapActions } from 'vuex';
import { INSTAGRAM_LOCALSTORAGE_EVENTS } from '@/globals/agent/instagram';
export default {
    components: {
        Header,
        Tab
    },
    methods: {
        ...mapActions([
            'agtInstagramDispositionChatHistoryInit',
            'agtInstagramDispositionChatOptionsInit',
            'agtInstagramSetConversationInfo',
            'agtInstagramDispositionChatSetFormFlag',
            'agtInstagramDispositionChatDetailInit'
        ]),
        closeEvent () {
            this.$refs.tabRef.closeEvent();
        },
        async updatedLocalStorage (event) {
            const conversationInfo =
        JSON.parse(localStorage.getItem('agtInstagramConversationInfo')) || null;
            const dispositionId = conversationInfo?.isDisposition
                ? conversationInfo?.client?.dispositionId || null
                : null;
            await this.agtInstagramSetConversationInfo(conversationInfo);
            await this.agtInstagramDispositionChatDetailInit({
                id: dispositionId
            });
            await this.agtInstagramDispositionChatOptionsInit({
                campaignId: conversationInfo?.campaignId || null
            });
            await this.agtInstagramDispositionChatHistoryInit({
                id: dispositionId
            });
            await this.agtInstagramDispositionChatSetFormFlag(!conversationInfo?.isDisposition);
        },
        async updateFlag () {
            const formToCreate =
        localStorage.getItem('agtInstagramDispositionChatFormToCreate') === 'true';
            await this.agtInstagramDispositionChatSetFormFlag(formToCreate);
        }
    },
    mounted () {
        window.parent.document.addEventListener(
            INSTAGRAM_LOCALSTORAGE_EVENTS.DISPOSITION.FORM_INIT_DATA,
            this.updatedLocalStorage
        );
    },
    beforeUnmount () {
        window.parent.document.removeEventListener(
            INSTAGRAM_LOCALSTORAGE_EVENTS.DISPOSITION.FORM_INIT_DATA,
            this.updatedLocalStorage
        );
    },
    async created () {
        await this.updatedLocalStorage();
    }
};
</script>
