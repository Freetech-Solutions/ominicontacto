import urls from '@/api_urls/supervisor/instagram/templates_urls';
import { BaseService } from '@/services/base_service';

export default class InstagramTemplateService extends BaseService {
    constructor () {
        super(urls, 'Instagram Templates');
    }

    async getTemplates (campaignId) {
        try {
            const resp = await fetch(this.urls.Templates(campaignId), this.payload);
            return await resp.json();
        } catch (error) {
            console.error(`Error al obtener < Instagram Templates >`);
            console.error(error);
            return [];
        } finally {
            this.initPayload();
        }
    }
}
