import WhatsappAgentRoutes from './whatsapp';
import FacebookAgentRoutes from './facebook';
import InstagramAgentRoutes from './instagram';
import EmailAgentRoutes from './email';

export const agentRoutes = [
    ...WhatsappAgentRoutes,
    ...FacebookAgentRoutes,
    ...InstagramAgentRoutes,
    ...EmailAgentRoutes
];
