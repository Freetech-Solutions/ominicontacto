import URLS from '@/api_urls/supervisor/instagram/reports/general_report_urls';
import { BaseService, HTTP } from '@/services/base_service';

export default class SupInstagramReportGeneralService extends BaseService {
    constructor () {
        super(URLS, 'Instagram <General Report>');
    }

    normalizeDate (date) {
        if (!date) {
            return null;
        }
        if (typeof date === 'string') {
            return date.slice(0, 10);
        }
        const month = `${date.getMonth() + 1}`.padStart(2, '0');
        const day = `${date.getDate()}`.padStart(2, '0');
        return `${date.getFullYear()}-${month}-${day}`;
    }

    async getGeneralInstagramReport ({
        campaignId = null,
        filters = { startDate: null, endDate: null }
    }) {
        try {
            this.setPayload(
                HTTP.POST,
                JSON.stringify({
                    start_date: this.normalizeDate(filters.startDate),
                    end_date: this.normalizeDate(filters.endDate),
                    campaign: campaignId
                })
            );
            const url = this.urls.SupInstagramReportGeneral();
            const resp = await fetch(url, this.payload);
            return await resp.json();
        } catch (error) {
            console.error(
                `Error al obtener < Reporte General de Instagram de la Campana (${campaignId}) >`
            );
            return [];
        } finally {
            this.initPayload();
        }
    }
}
