export default {
    agtInstagramTransferChatInitData (state, data) {
        state.agtInstagramTransferChatForm = {
            to: data?.to,
            conversationId: data?.conversationId
        };
    },
    agtInstagramTransferChatInitAgents (state, data) {
        state.agtInstagramTransferChatAgents = data;
    }
};
