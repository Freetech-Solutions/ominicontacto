import Index from '@/views/supervisor/instagram/reports/campaign/conversation_report/Index';
import { INSTAGRAM_REPORTS_URL_NAME } from '@/globals/supervisor/instagram';

export default [
    {
        path: `/${INSTAGRAM_REPORTS_URL_NAME}_campaign_conversations.html`,
        name: `${INSTAGRAM_REPORTS_URL_NAME}_campaign_conversations`,
        component: Index
    }
];
