export default {
    initSupInstagramReportCampaignConversations (state, conversations) {
        state.supInstagramReportCampaignConversations = conversations;
    },
    initSupInstagramReportCampaignAgents (state, agents) {
        state.supInstagramReportCampaignAgents = agents.map((agent) => {
            return {
                value: agent.agent_id,
                name: agent.agent_full_name
            };
        });
    }
};
