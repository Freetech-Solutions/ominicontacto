<template>
  <div>
    <HeaderMessages />
    <TabView>
      <TabPanel>
        <template #header>
          <span>{{ $t("views.whatsapp.conversations.answered") }}</span>
          <Badge :value="numAnsweredMessages.toString()" class="ml-2"></Badge>
        </template>
        <ListMessages :messages="answeredMessages" class="scroll" />
      </TabPanel>
      <TabPanel>
        <template #header>
          <span>{{ $t("views.whatsapp.conversations.new") }}</span>
          <Badge :value="numNewMessages.toString()" class="ml-2"></Badge>
        </template>
        <ListMessages :messages="newMessages" class="scroll" />
      </TabPanel>
    </TabView>
  </div>
</template>

<script>
import { mapActions, mapState } from 'vuex';
import HeaderMessages from '@/components/agent/instagram/messages/HeaderMessages';
import ListMessages from '@/components/agent/instagram/messages/ListMessages';
import { InstagramConsumer } from '@/web_sockets/instagram_consumer';

export default {
    components: {
        HeaderMessages,
        ListMessages
    },
    computed: {
        ...mapState(['agtInstagramChatsList'])
    },
    async created () {
        this.resetLocalStorage();
        if (!this.consumer) {
            this.consumer = InstagramConsumer.getInstance({
                $t: this.$t
            });
        }
        console.log('RESET LOCALSTORAGE ON INSTAGRAM INDEX');
        await this.agtInstagramChatsListInit();
    },
    mounted () {
        window.addEventListener('storage', this.updatedLocalStorage);
        this.updatedLocalStorage();
    },
    beforeUnmount () {
        window.removeEventListener('storage', this.updatedLocalStorage);
    },
    methods: {
        ...mapActions(['agtInstagramChatsListInit']),
        resetLocalStorage () {
            localStorage.setItem('agtInstagramConversationCreatedId', null);
            localStorage.setItem('agtInstagramConversationAttending', null);
            localStorage.setItem('agtInstagramConversationId', null);
            localStorage.setItem('agtInstagramConversationMessages', null);
            localStorage.setItem('agtInstagramMessageInfo', null);
            localStorage.setItem('onlyInstagramTemplates', null);
            localStorage.setItem('agtInstagramConversationNewResetForm', null);
            localStorage.setItem('agtInstagramConversationInfo', JSON.stringify(null));
        },
        updatedLocalStorage () {
            const conversationId = localStorage.getItem('agtInstagramConversationCreatedId');
            const parsedConversationId = parseInt(conversationId);
            if (conversationId && conversationId !== 'null' && !Number.isNaN(parsedConversationId)) {
                this.$router.push({
                    name: 'agent_instagram_conversation_detail',
                    params: { id: parsedConversationId }
                });
                localStorage.setItem('agtInstagramConversationCreatedId', null);
            }
        }
    },
    data () {
        return {
            consumer: null,
            newMessages: [],
            answeredMessages: [],
            numNewMessages: 0,
            numAnsweredMessages: 0
        };
    },
    watch: {
        agtInstagramChatsList: {
            handler () {
                this.newMessages = this.agtInstagramChatsList.filter(
                    (m) => m.isNew === true
                );
                this.answeredMessages = this.agtInstagramChatsList.filter(
                    (m) => m.isNew === false
                );
                this.numNewMessages = this.agtInstagramChatsList.filter(
                    (m) => m.isNew === true && m.answered === false
                ).length;
                this.numAnsweredMessages = this.agtInstagramChatsList.filter(
                    (m) => m.isNew === false && m.answered === false
                ).length;
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
  height: calc(100vh - 250px);
}
</style>
