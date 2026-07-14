/* eslint-disable no-unused-vars */
import { HTTP_STATUS } from '@/globals';
import AccountService from '@/services/supervisor/instagram/wizard_account_service';
const service = new AccountService();

export default {
    async initInstagramAccounts({ commit }) {
        const { status, data } = await service.list();
        commit('initInstagramAccounts', status === HTTP_STATUS.SUCCESS ? data : []);
    },
    async initInstagramAccount({ commit }, { id = null, page = null }) {
        if (page) {
            commit('initInstagramAccount', page);
        } else if (id) {
            const { status, data } = await service.detail(id);
            commit('initInstagramAccount', status === HTTP_STATUS.SUCCESS ? data : null);
        } else {
            commit('initInstagramAccount', null);
        }
    },
    async createInstagramAccount({ commit }, data) {
        return await service.create(data);
    },
    async updateInstagramAccount({ commit }, { id, data }) {
        return await service.update(id, data);
    },
    async deleteInstagramAccount({ commit }, id) {
        return await service.delete(id);
    },
    initFormFlag({ commit }, flag = false) {
        commit('initFormFlag', flag);
    },
    async initInstagramAccountCampaigns({ commit }) {
        try {
            const response = await service.getCampaigns();
            const { status, data } = response;
            commit('initInstagramAccountCampaigns', status === HTTP_STATUS.SUCCESS ? data : []);
            return response;
        } catch (error) {
            console.error('Error al obtener las campañas');
            console.error(error);
            commit('initInstagramAccountCampaigns', []);
            return {
                status: HTTP_STATUS.ERROR,
                message: 'Error al obtener las campañas'
            };
        }
    },
    initInstagramAccountOptionForm({ commit }, option = null) {
        commit('initInstagramAccountOptionForm', option);
    },
    createInstagramAccountOption({ commit }, { data, menuId }) {
        commit('createInstagramAccountOption', { data, menuId });
    },
    updateInstagramAccountOption({ commit }, { id, data, menuId }) {
        commit('updateInstagramAccountOption', { id, data, menuId });
    },
    deleteInstagramAccountOption({ commit }, { id, menuId }) {
        commit('deleteInstagramAccountOption', { id, menuId });
    }
};
