const BASE_ROUTE = '/api/v1/instagram/chat';

export default {
    /** url name='api_campaign_instagram_report_conversations' */
    SupInstagramReportCampaignConversations: (campaignId = null) =>
        `${BASE_ROUTE}/${campaignId}/filter_chats`,
    /** url name='api_campaign_instagram_report_conversation_detail' */
    SupInstagramReportCampaignConversationDetail: (conversationId = null) =>
        `${BASE_ROUTE}/${conversationId}/report_detail`,
    /** url name='api_agents_campaign' */
    SupInstagramReportCampaignAgents: (campaignId) =>
        `/api/v1/campaign/${campaignId}/agents/`
};
