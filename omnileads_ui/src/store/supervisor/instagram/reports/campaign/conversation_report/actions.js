/* eslint-disable no-unused-vars */
import { HTTP_STATUS } from '@/globals';
import Service from '@/services/supervisor/instagram/reports/campaign/conversation_report_service';
const service = new Service();

const getMessageInfo = ({ $t, data = null, itsMine = true }) => {
    const senderName = data && data.sender && data.sender.name ? data.sender.name : null;
    const senderPhone = data && data.sender && data.sender.phone
        ? data.sender.phone
        : $t('globals.whatsapp.automatic_agent');
    let clientName = '-';
    if (data && data.contact_data) {
        if (data.contact_data.nombre) {
            clientName = data.contact_data.nombre;
        } else if (data.contact_data.name) {
            clientName = data.contact_data.name;
        }
    }
    return {
        id: data.id,
        from: itsMine
            ? `${$t('globals.agent')} (${senderName || senderPhone})`
            : clientName || senderName || senderPhone,
        conversationId: data && data.conversation ? data.conversation : null,
        itsMine,
        message: data && data.content && data.content ? data.content : '',
        status: data && data.status ? data.status : null,
        fail_reason: data && data.fail_reason ? data.fail_reason : null,
        date: data && data.timestamp ? new Date(data.timestamp) : null,
        type: data && data.type ? data.type : null,
        file: data && data.file ? data.file : null
    };
};

export default {
    async initSupInstagramReportCampaignConversations (
        { commit },
        {
            campaignId = null,
            filters = {
                startDate: null,
                endDate: null,
                phone: null,
                agents: null
            }
        }
    ) {
        try {
            const { status, data } =
                await service.getCampaignReportConversations({
                    campaignId,
                    filters
                });
            commit(
                'initSupInstagramReportCampaignConversations',
                status === HTTP_STATUS.SUCCESS ? data : []
            );
        } catch (error) {
            console.error(
                `===> Error al obtener < Reporte de Conversaciones Instagram de la Campana (${campaignId}) >`
            );
            console.error(error);
            commit('initSupInstagramReportCampaignConversations', []);
        }
    },
    async initSupInstagramReportCampaignAgents ({ commit }, { campaignId = null }) {
        try {
            const { status, agentsCampaign } =
                await service.getCampaignReportAgents({
                    campaignId
                });
            commit(
                'initSupInstagramReportCampaignAgents',
                status === HTTP_STATUS.SUCCESS ? agentsCampaign : []
            );
        } catch (error) {
            console.error(
                `===> Error al obtener < Agentes de la Campana (${campaignId}) para Instagram >`
            );
            console.error(error);
            commit('initSupInstagramReportCampaignAgents', []);
        }
    },
    async initSupInstagramReportCampaignConversationDetail (
        { commit },
        { conversationId = null, $t }
    ) {
        try {
            if (!conversationId) {
                commit('agtInstagramConversationInitMessages', []);
                commit('agtInstagramConversationInfoInit', {});
                return;
            }
            const { status, data } =
                await service.getCampaignReportConversationDetail({ conversationId });
            if (status === HTTP_STATUS.SUCCESS) {
                commit(
                    'agtInstagramConversationInitMessages',
                    data.messages.map((msg) => {
                        const itsMine = msg.origin === data.page.page_id;
                        return getMessageInfo({ $t, data: msg, itsMine });
                    })
                );
                commit('agtInstagramConversationInfoInit', data);
                return;
            }
            commit('agtInstagramConversationInitMessages', []);
            commit('agtInstagramConversationInfoInit', {});
        } catch (error) {
            console.error(
                `===> Error al obtener < Detalle Conversacion Instagram (${conversationId}) >`
            );
            console.error(error);
            commit('agtInstagramConversationInitMessages', []);
            commit('agtInstagramConversationInfoInit', {});
        }
    }
};
