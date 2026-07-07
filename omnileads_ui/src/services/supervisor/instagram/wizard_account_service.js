import urls from '@/api_urls/supervisor/instagram/account_urls';
import { BaseService } from '@/services/base_service';

export default class AccountService extends BaseService {
    constructor () {
        super(urls, 'Cuenta de Instagram');
    }

    async getCampaigns () {
        try {
            const resp = await fetch(this.urls.Campaigns, this.payload);
            return await resp.json();
        } catch (error) {
            console.error(`Error al obtener < Campanas >`);
            return [];
        } finally {
            this.initPayload();
        }
    }
}
