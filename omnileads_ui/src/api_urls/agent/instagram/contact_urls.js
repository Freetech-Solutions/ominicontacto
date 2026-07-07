export default {
    ContactList: (campaignId) => `/api/v1/instagram/contact/${campaignId}`,
    ContactCreateFromConversation: (campaignId, conversationId) => `/api/v1/instagram/contact/${campaignId}/create_contact_from_conversation/${conversationId}`,
    ContactCreate: (campaignId) => `/api/v1/instagram/contact/${campaignId}`,
    ContactUpdate: (campaignId, contactId) => `/api/v1/instagram/contact/${campaignId}/${contactId}`,
    ContactCampaignDBFields: (campaignId) => `/api/v1/instagram/contact/${campaignId}/db_fields`,
    ContactSearch: (campaignId) => `/api/v1/instagram/contact/${campaignId}/search`,
    ContactSuggestMatch: (campaignId) => `/api/v1/instagram/contact/${campaignId}/suggest_match`,
    ContactAssignToConversation: (conversationId) => `/api/v1/instagram/chat/${conversationId}/assign_contact`
};
