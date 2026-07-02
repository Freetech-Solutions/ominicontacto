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
            const parsedId = rawId && rawId !== 'null' ? parseInt(rawId, 10) : null;

            if (!parsedId || Number.isNaN(parsedId)) return;

            this.conversationId = parsedId;

            await this.agtWhatsLastConversationDetail({
                conversationId: parsedId,
                $t: this.$t
            });
        }
    },
    async mounted () {
        await this.loadConversation();
    }
};
</script>
