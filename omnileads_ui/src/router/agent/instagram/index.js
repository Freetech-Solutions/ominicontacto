import Index from '@/views/agent/instagram/Index';
import ConversationRoutes from './conversation_routes';
import TemplateRoutes from './template_routes';
import DispositionChatRoutes from './disposition_chat_routes';
import MessageTransferRoutes from './message_transfer_routes';
import ContactRoutes from './contact_routes';
import { INSTAGRAM_URL_NAME } from '@/globals/agent/instagram';

export default [
    {
        path: `/${INSTAGRAM_URL_NAME}_index.html`,
        name: `${INSTAGRAM_URL_NAME}`,
        component: Index
    },
    ...ConversationRoutes,
    ...TemplateRoutes,
    ...DispositionChatRoutes,
    ...MessageTransferRoutes,
    ...ContactRoutes
];
