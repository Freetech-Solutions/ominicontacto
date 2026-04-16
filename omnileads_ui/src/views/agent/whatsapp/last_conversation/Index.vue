<template>
  <div class="h-full">
    <LastConversationMessages v-if="conversationId" />
  </div>
</template>

<script>
import { mapActions } from 'vuex';
import LastConversationMessages from '@/components/agent/whatsapp/conversation/LastConversationMessages.vue';

export default {
    components: {
        LastConversationMessages
    },
    data () {
        return {
            conversationId: null
        };
    },
    methods: {
        ...mapActions([
            'agtWhatsLastConversationDetail'
        ]),
        async loadConversation () {
            const rawId = localStorage.getItem('agtWhatsLastConversationId');
            const parsedId = rawId ? parseInt(rawId) : null;

            console.log('mounted loadConversation', rawId, parsedId);

            if (!parsedId || Number.isNaN(parsedId)) return;

            this.conversationId = parsedId;

            await this.agtWhatsLastConversationDetail({
                conversationId: parsedId,
                $t: this.$t
            });

            console.log('action called with', parsedId);
        }
    },
    async mounted () {
        await this.loadConversation();
    }
};
</script>
