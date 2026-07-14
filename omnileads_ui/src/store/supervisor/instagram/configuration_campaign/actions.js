/* eslint-disable no-unused-vars */
import { HTTP_STATUS } from '@/globals';
import Service from '@/services/supervisor/instagram/templates_service';
const service = new Service();

export default {
    async initSupCampaignInstagramTemplates ({ commit }, { campaignId = null }) {
        try {
            commit('initSupCampaignInstagramTemplates', []);
            if (!campaignId) {
                return {
                    status: HTTP_STATUS.ERROR,
                    message: 'Error al obtener los templates'
                };
            }
            const response = await service.getTemplates(campaignId);
            const { status, data } = response;
            const templates = status === HTTP_STATUS.SUCCESS
                ? data.instagram_templates || []
                : [];
            commit('initSupCampaignInstagramTemplates', templates);
            return response;
        } catch (error) {
            console.error('Error al obtener los templates');
            console.error(error);
            commit('initSupCampaignInstagramTemplates', []);
            return {
                status: HTTP_STATUS.ERROR,
                message: 'Error al obtener los templates'
            };
        }
    }
};
