import URLS from '@/api_urls/supervisor/instagram/reports/campaign/conversation_report_urls';
import { BaseService, HTTP } from '@/services/base_service';

export default class SupInstagramReportCampaignConversationService extends BaseService {
    constructor () {
        super(URLS, 'Instagram <Campaign Conversation Report>');
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

    async getCampaignReportConversations ({
        campaignId = null,
        filters = { startDate: null, endDate: null, phone: null, agents: null }
    }) {
        try {
            this.setPayload(HTTP.POST, JSON.stringify({
                start_date: this.normalizeDate(filters.startDate),
                end_date: this.normalizeDate(filters.endDate),
                phone: filters.phone,
                agents: filters.agents
            }));
            const url = this.urls.SupInstagramReportCampaignConversations(campaignId);
            const resp = await fetch(url, this.payload);
            return await resp.json();
        } catch (error) {
            console.error(
                `Error al obtener < Reporte de Conversaciones Instagram de la Campana (${campaignId}) >`
            );
            return [];
        } finally {
            this.initPayload();
        }
    }

    async getCampaignReportConversationDetail ({ conversationId = null }) {
        try {
            const url = this.urls.SupInstagramReportCampaignConversationDetail(conversationId);
            const resp = await fetch(url, this.payload);
            return await resp.json();
        } catch (error) {
            console.error(
                `Error al obtener < Detalle Conversacion Instagram (${conversationId}) >`
            );
            return [];
        } finally {
            this.initPayload();
        }
    }

    async getCampaignReportAgents ({ campaignId = null }) {
        try {
            const url = this.urls.SupInstagramReportCampaignAgents(campaignId);
            const resp = await fetch(url, this.payload);
            return await resp.json();
        } catch (error) {
            console.error(
                `Error al obtener < Agentes de la Campana (${campaignId}) para Instagram >`
            );
            return [];
        } finally {
            this.initPayload();
        }
    }
}
