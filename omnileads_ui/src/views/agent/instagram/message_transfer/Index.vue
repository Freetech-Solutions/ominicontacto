<template>
  <div>
    <Header @handleCloseEvent="closeEvent" />
    <Form ref="formRef" />
  </div>
</template>

<script>
import Header from '@/components/agent/instagram/message_transfer/Header';
import Form from '@/components/agent/instagram/message_transfer/Form';
import { INSTAGRAM_LOCALSTORAGE_EVENTS } from '@/globals/agent/instagram';
import { mapActions } from 'vuex';
export default {
    components: {
        Header,
        Form
    },
    methods: {
        ...mapActions([
            'agtInstagramTransferChatInitData',
            'agtInstagramSetConversationInfo'
        ]),
        closeEvent () {
            this.$refs.formRef.clearData();
        },
        async updatedLocalStorage (event) {
            const conversationInfo =
        JSON.parse(localStorage.getItem('agtInstagramConversationInfo')) || null;
            await this.agtInstagramSetConversationInfo(conversationInfo);
            await this.agtInstagramTransferChatInitData({
                campaingId: conversationInfo?.campaignId || null
            });
        }
    },
    mounted () {
        window.parent.document.addEventListener(
            INSTAGRAM_LOCALSTORAGE_EVENTS.TRANSFER.FORM_INIT_DATA,
            this.updatedLocalStorage
        );
    },
    beforeUnmount () {
        window.parent.document.removeEventListener(
            INSTAGRAM_LOCALSTORAGE_EVENTS.TRANSFER.FORM_INIT_DATA,
            this.updatedLocalStorage
        );
    },
    async created () {
        await this.updatedLocalStorage();
    }
};
</script>
