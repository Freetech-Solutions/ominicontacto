import Index from '@/views/agent/instagram/contact/Index';
import { INSTAGRAM_URL_NAME } from '@/globals/agent/instagram';

export default [
    {
        path: `/${INSTAGRAM_URL_NAME}_contact_form.html`,
        name: `${INSTAGRAM_URL_NAME}_contact_form`,
        component: Index
    }
];
