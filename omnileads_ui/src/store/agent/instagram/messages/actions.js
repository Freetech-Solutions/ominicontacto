/* eslint-disable no-unused-vars */
export default {
    agtInstagramSendMessageStatus ({ commit }, info = null) {
        try {
            commit('agtInstagramSendMessageStatus', info);
        } catch (error) {
            console.error('===> ERROR al actualizar el status del mensaje');
            console.error(error);
            commit('agtInstagramSendMessageStatus', null);
        }
    }
};
