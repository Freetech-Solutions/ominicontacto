import {
    AgentWhatsappActions,
    AgentWhatsappMutations,
    AgentWhatsappState,
    AgentWhatsappGetters
} from './whatsapp';
import {
    AgentFacebookActions,
    AgentFacebookMutations,
    AgentFacebookState,
    AgentFacebookGetters
} from './facebook';
import {
    AgentInstagramActions,
    AgentInstagramMutations,
    AgentInstagramState,
    AgentInstagramGetters
} from './instagram';

export const agentState = {
    ...AgentWhatsappState,
    ...AgentFacebookState,
    ...AgentInstagramState
};

export const agentMutations = {
    ...AgentWhatsappMutations,
    ...AgentFacebookMutations,
    ...AgentInstagramMutations
};

export const agentActions = {
    ...AgentWhatsappActions,
    ...AgentFacebookActions,
    ...AgentInstagramActions
};

export const agentGetters = {
    ...AgentWhatsappGetters,
    ...AgentFacebookGetters,
    ...AgentInstagramGetters
};
