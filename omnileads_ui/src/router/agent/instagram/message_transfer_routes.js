import Index from '@/views/agent/instagram/message_transfer/Index';
import { INSTAGRAM_URL_NAME } from '@/globals/agent/instagram';

export default [
    {
        path: `/${INSTAGRAM_URL_NAME}_message_transfer.html`,
        name: `${INSTAGRAM_URL_NAME}_message_transfer`,
        component: Index
    }
];
