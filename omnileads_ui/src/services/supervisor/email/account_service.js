import urls from '@/api_urls/supervisor/email/account_urls';
import { BaseService } from '@/services/base_service';

export default class AccountService extends BaseService {
    constructor () {
        super(urls, 'Cuenta de Email');
    }
}
