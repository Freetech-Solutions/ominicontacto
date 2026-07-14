import Index from '@/views/supervisor/instagram/reports/general/Index';
import { INSTAGRAM_REPORTS_URL_NAME } from '@/globals/supervisor/instagram';

export default [
    {
        path: `/${INSTAGRAM_REPORTS_URL_NAME}_general.html`,
        name: `${INSTAGRAM_REPORTS_URL_NAME}_general`,
        component: Index
    }
];
