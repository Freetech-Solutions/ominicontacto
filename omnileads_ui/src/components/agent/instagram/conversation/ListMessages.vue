<template>
  <div @scroll="onScroll" ref="scrollContainer">
    <div class="grid mb-2 mx-1" v-for="message in agtInstagramConversationMessages" :key="message.id">
      <div class="col">
        <Message :message="message" />
      </div>
    </div>
  </div>
</template>

<script>
import { mapState, mapActions } from 'vuex';
import Message from '@/components/agent/instagram/conversation/Message';

export default {
    data () {
        return {
            scrollTimeout: null
        };
    },
    computed: {
        ...mapState(['agtInstagramConversationMessages'])
    },
    components: {
        Message
    },
    methods: {
        ...mapActions(['agtInstagramMarkMessageAsRead']),
        onScroll () {},
        async markItAsRead (notReadMessageIds) {
            return await this.agtInstagramMarkMessageAsRead(notReadMessageIds);
        },
        scrollToBottom () {
            if (!this.$refs.scrollContainer) {
                return;
            }
            this.$refs.scrollContainer.scroll({
                top: this.$refs.scrollContainer.scrollHeight,
                behavior: 'smooth'
            });
        }
    },
    watch: {
        agtInstagramConversationMessages: {
            handler (newMsgs = []) {
                const notReadMessageIds = newMsgs
                    .filter((msg) => msg.status !== 'read')
                    .map((msg) => msg.id);

                if (this.scrollTimeout) {
                    clearTimeout(this.scrollTimeout);
                }

                this.scrollTimeout = setTimeout(() => {
                    this.scrollToBottom();
                    if (notReadMessageIds.length) {
                        this.markItAsRead(notReadMessageIds);
                    }
                    this.scrollTimeout = null;
                }, 50);
            },
            deep: true,
            immediate: true
        }
    }

};
</script>
