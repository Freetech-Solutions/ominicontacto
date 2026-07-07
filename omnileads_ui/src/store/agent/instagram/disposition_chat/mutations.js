/* eslint-disable */
const getContactData = (contact =  null) => {
    return {
        id: contact && contact.id ? contact.id : null,
        phone: contact && contact.phone ? contact.phone : null,
        data: contact && contact.data ? contact.data : null,
        disposition: contact && contact.disposition ? contact.disposition : null
    };
};

const getAgentData = (agent = null) => {
    return {
        id: agent && agent.id ? agent.id : null,
        name: agent && agent.name ? agent.name : null,
        email: agent && agent.email ? agent.email : null
    };
};

export default {
    agtInstagramDispositionChatHistoryInit (state, history = []) {
        state.agtInstagramDispositionChatHistory = history;
    },
    agtInstagramDispositionChatOptionsInit (state, options = []) {
        state.agtInstagramDispositionChatOptions = options;
    },
    agtInstagramDispositionChatDetailInit (state, dispositionChat = null) {
        state.agtInstagramDispositionChatDetail = {
            id: dispositionChat && dispositionChat.id ? dispositionChat.id : null,
            contact: getContactData(dispositionChat && dispositionChat.contact ? dispositionChat.contact : null),
            agent: getAgentData(dispositionChat && dispositionChat.agent ? dispositionChat.agent : null),
            comments: dispositionChat && dispositionChat.comments ? dispositionChat.comments : null,
            form_response: dispositionChat && dispositionChat.form_response
                ? dispositionChat.form_response
                : null,
            disposition_data: dispositionChat && dispositionChat.disposition_data
                ? dispositionChat.disposition_data
                : null
        };
    },
    agtInstagramDispositionChatSetFormFlag (state, flag = true) {
        state.agtInstagramDispositionChatFormToCreate = flag;
    }
};
