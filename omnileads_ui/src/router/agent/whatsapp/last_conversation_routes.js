import Index from '@/views/agent/whatsapp/last_conversation/Index';
import { WHATSAPP_URL_NAME } from '@/globals/agent/whatsapp';

export default [
    {
        path: `/${WHATSAPP_URL_NAME}_last_conversation.html`,
        name: `${WHATSAPP_URL_NAME}_last_conversation`,
        component: Index
    }
];
