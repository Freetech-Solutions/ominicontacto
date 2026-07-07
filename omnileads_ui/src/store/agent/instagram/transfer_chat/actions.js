/* eslint-disable no-unused-vars */
import InstagramTransferChatService from '@/services/agent/instagram/transfer_service';
import { HTTP_STATUS } from '@/globals';
const transferService = new InstagramTransferChatService();

export default {
    async agtInstagramTransferChatInitData ({ commit }, { campaingId = null }) {
        try {
            if (!campaingId) {
                await commit('agtInstagramTransferChatInitAgents', []);
                return {
                    status: HTTP_STATUS.ERROR,
                    message: 'Error al obtener Agentes'
                };
            }
            const response = await transferService.getActiveAgents({
                campaingId
            });
            const { status, data } = response;
            await commit(
                'agtInstagramTransferChatInitAgents',
                status === HTTP_STATUS.SUCCESS ? data : []
            );
            return response;
        } catch (error) {
            console.error('agtInstagramTransferChatInitData');
            console.error(error);
            await commit('agtInstagramTransferChatInitAgents', []);
        }
    },
    async agtInstagramTransferChatSend ({ commit }, postData) {
        const { status } = await transferService.transferToagent(postData);
        if (status === HTTP_STATUS.SUCCESS) {
            return {
                status: HTTP_STATUS.SUCCESS,
                message: 'Se transfirio satisfactoriamente el chat'
            };
        } else {
            return {
                status: HTTP_STATUS.ERROR,
                message: 'No se pudo transferir el chat'
            };
        }
    }
};
