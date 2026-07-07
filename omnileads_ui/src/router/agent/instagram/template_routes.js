import Index from '@/views/agent/instagram/templates/Index';
import { INSTAGRAM_URL_NAME } from '@/globals/agent/instagram';

export default [
    {
        path: `/${INSTAGRAM_URL_NAME}_templates.html`,
        name: `${INSTAGRAM_URL_NAME}_templates`,
        component: Index
    }
];
