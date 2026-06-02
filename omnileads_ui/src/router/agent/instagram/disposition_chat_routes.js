import Index from '@/views/agent/instagram/disposition_chat/Index';
import { INSTAGRAM_URL_NAME } from '@/globals/agent/instagram';

export default [
    {
        path: `/${INSTAGRAM_URL_NAME}_disposition_chat.html`,
        name: `${INSTAGRAM_URL_NAME}_disposition_chat`,
        component: Index
    }
];
