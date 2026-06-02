import WhatsappAgentRoutes from './whatsapp';
import FacebookAgentRoutes from './facebook';
import InstagramAgentRoutes from './instagram';

export const agentRoutes = [
    ...WhatsappAgentRoutes,
    ...FacebookAgentRoutes,
    ...InstagramAgentRoutes
];
