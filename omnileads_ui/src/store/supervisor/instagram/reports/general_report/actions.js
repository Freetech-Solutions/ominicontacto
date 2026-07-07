/* eslint-disable no-unused-vars */
import { HTTP_STATUS } from '@/globals';
import Service from '@/services/supervisor/instagram/reports/general_report_service';
const service = new Service();

export default {
    async initSupInstagramReportGeneral (
        { commit },
        {
            campaignId = null,
            filters = {
                startDate: null,
                endDate: null
            }
        }
    ) {
        try {
            const response = await service.getGeneralInstagramReport({
                campaignId,
                filters
            });
            const { status, data } = response;
            commit(
                'initSupInstagramReportGeneral',
                status === HTTP_STATUS.SUCCESS ? data : null
            );
            return response;
        } catch (error) {
            console.error(
                `===> Error al obtener < Reporte General de Instagram de la Campana (${campaignId}) >`
            );
            console.error(error);
            commit('initSupInstagramReportGeneral', null);
            return {
                status: HTTP_STATUS.ERROR,
                message: 'Error al obtener Reporte General de Instagram'
            };
        }
    },
    initSupInstagramReportGeneralColors ({ commit }, { rgbColors, rgbaColors }) {
        commit('initSupInstagramReportGeneralColors', { rgbColors, rgbaColors });
    }
};
