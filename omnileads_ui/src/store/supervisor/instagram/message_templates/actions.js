/* eslint-disable no-unused-vars */
import MessageTemplateService from '@/services/supervisor/instagram/message_template_service';
const service = new MessageTemplateService();

export default {
    async initInstagramAccountTemplates({ commit }) {
        const { status, data } = await service.list();
        commit('initInstagramAccountTemplates', status === 'SUCCESS' ? data : []);
    },
    async initInstagramAccountTemplate({ commit }, { id = null, messageTemplate = null }) {
        if (messageTemplate) {
            commit('initInstagramAccountTemplate', messageTemplate);
        } else if (id) {
            const { status, data } = await service.detail(id);
            commit('initInstagramAccountTemplate', status === 'SUCCESS' ? data : null);
        } else {
            commit('initInstagramAccountTemplate', null);
        }
    },
    initInstagramAccountTemplateFormFields({ commit }, { type = null, config = null }) {
        commit('initInstagramAccountTemplateFormFields', { type, config });
    },
    async createInstagramAccountTemplate({ commit }, data) {
        return await service.create(data);
    },
    async updateInstagramAccountTemplate({ commit }, { id, data }) {
        return await service.update(id, data);
    },
    async deleteInstagramAccountTemplate({ commit }, id) {
        return await service.delete(id);
    }
};
