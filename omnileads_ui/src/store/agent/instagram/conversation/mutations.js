import {
    notificationEvent,
    NOTIFICATION
} from '@/globals/agent/instagram';

const setClientInfo = (info = null) => {
    return {
        id: info && info.id ? info.id : null,
        phone: info && info.phone ? info.phone : null,
        ig_scoped_id: info && info.ig_scoped_id ? info.ig_scoped_id : null,
        data: info && info.data ? info.data : null,
        dispositionId: info && info.disposition ? info.disposition : null
    };
};

const setPageInfo = (info = null) => {
    return {
        id: info && info.id ? info.id : null,
        name: info && info.name ? info.name : null,
        page_id: info && info.page_id ? info.page_id : null
    };
};

const getCampaignId = (info = null) => {
    if (!info) return null;
    return info.campaign_id || info.campaing_id || info.campaignId || null;
};

const getCampaignName = (info = null) => {
    if (!info) return null;
    return info.campaign_name || info.campaing_name || info.campaignName || null;
};

const setFromInfo = (info = null) => {
    if (info && info.client) {
        if (info.client.data.nombre) {
            return info.client.data.nombre;
        }
        if (info.client.data.name) {
            return info.client.data.name;
        }
    } else if (info && info.client_alias) {
        return info.client_alias;
    }
    return info.destination;
};

export default {
    agtInstagramConversationSendMessage (state, message) {
        state.agtInstagramConversationMessages.push(message);
    },
    agtInstagramConversationSendTemplateMessage (state, messages) {
        state.agtInstagramConversationMessages = [...messages];
    },
    agtInstagramConversationReciveMessage (state, data = null) {
        if (!data) return;
        const messages = state.agtInstagramConversationMessages;
        const newMessageId = data && data.message_id ? data.message_id : null;
        const alreadyExists = messages.find(m => m.id === newMessageId);
        if (!alreadyExists) {
            const itsMine = data && data.origin ? data.origin === data.page_id : false;
            const senderName = data && data.sender && data.sender.name ? data.sender.name : null;
            const senderPhone = data && data.sender && data.sender.phone ? data.sender.phone : '------';
            var clientName = '-';
            if (data && data.contact_data) {
                if (data.contact_data.nombre) {
                    clientName = data.contact_data.nombre;
                } else if (data.contact_data.name) {
                    clientName = data.contact_data.name;
                }
            }
            const message = {
                id: newMessageId,
                from: itsMine
                    ? `Agente (${senderName})`
                    : clientName || senderPhone,
                conversationId: data && data.chat_id ? data.chat_id : null,
                itsMine,
                message: data && data.content ? data.content : '',
                status: data && data.status ? data.status : null,
                date: data && data.timestamp ? new Date(data.timestamp) : new Date(),
                type: data && data.type ? data.type : null
            };
            if (Number(localStorage.getItem('agtInstagramConversationAttending')) !== data.chat_id) {
                notificationEvent(
                    NOTIFICATION.TITLES.INSTAGRAM_NEW_MESSAGE,
                    `Mensaje Nuevo de ${clientName || senderName || senderPhone}`,
                    NOTIFICATION.ICONS.INFO
                );
                var a = state.agtInstagramChatsList.find(m => m.id === data.chat_id);
                a.numMessagesUnread = a.numMessagesUnread + 1;
                console.log('*******', a.numMessagesUnread);
            } else {
                state.agtInstagramConversationMessages.push(message);
            }
        }
    },
    agtInstagramConversationInitMessages (state, messages) {
        console.log('agtInstagramConversationInitMessages >>', messages);
        // Reemplazamos el array completo para que Vue detecte cambios
        state.agtInstagramConversationMessages = [...messages];
    },
    agtInstagramConversationInfoInit (state, conversation = null) {
        console.log('agtInstagramConversationInfoInit >>', conversation);
        state.agtInstagramConversationInfo = {
            id: conversation && conversation.id ? conversation.id : null,
            campaignId: getCampaignId(conversation),
            campaignName: getCampaignName(conversation),
            ig_scoped_id:
                conversation && conversation.destination
                    ? conversation.destination
                    : null,
            agent:
                conversation && conversation.agent ? conversation.agent : null,
            transferAgent:
                conversation && conversation.transfer_agent
                    ? conversation.transfer_agent
                    : null,
            isActive:
                conversation && conversation.is_active
                    ? conversation.is_active
                    : null,
            isDisposition:
                conversation && conversation.is_disposition
                    ? conversation.is_disposition
                    : null,
            expire:
                conversation && conversation.expire
                    ? conversation.expire
                    : null,
            timestamp:
                conversation && conversation.timestamp
                    ? conversation.timestamp
                    : null,
            messageNumber:
                conversation && conversation.message_number
                    ? conversation.message_number
                    : null,
            messageUnreadNumber:
                    conversation && conversation.message_unread
                        ? conversation.message_unread
                        : null,
            photo:
                conversation && conversation.photo ? conversation.photo : null,
            client: setClientInfo(
                conversation && conversation.client ? conversation.client : null
            ),
            page: setPageInfo(
                conversation && conversation.page ? conversation.page : null
            ),
            error:
                conversation && conversation.error ? conversation.error : false,
            errorEx:
                conversation && conversation.error_ex ? conversation.error_ex : null,
            client_alias:
                conversation && conversation.client_alias ? conversation.client_alias : null,
            isOutbound:
                conversation && conversation.saliente ? conversation.saliente : false
        };
        console.log('agtInstagramConversationInfo ******', state.agtInstagramConversationInfo);
    },
    agtInstagramChatsListInit (state, { isNew, inProgress }) {
        const chats = [];
        isNew.forEach((e = null) => {
            if (e) {
                chats.push({
                    id: e.id ? e.id : null,
                    from: setFromInfo(e),
                    campaignId: getCampaignId(e),
                    campaignName: getCampaignName(e) || '-------',
                    numMessages: e.message_number ? e.message_number : 0,
                    numMessagesUnread: e.message_unread ? e.message_unread : 0,
                    photo: e.photo ? e.photo : '',
                    isNew: true,
                    isMine: false,
                    isOutbound: e.saliente ? e.saliente : false,
                    answered: false,
                    transferAgent: e.transfer_agent ? e.transfer_agent : null,
                    date: e.timestamp ? new Date(e.timestamp) : null,
                    expire: e.expire ? new Date(e.expire) : null,
                    errorEx: e.error_ex ? e.error_ex : null,
                    error: e.error ? e.error : false
                });
            }
        });
        inProgress.forEach((e = null) => {
            if (e) {
                chats.push({
                    id: e.id ? e.id : null,
                    from: setFromInfo(e),
                    campaignId: getCampaignId(e),
                    campaignName: getCampaignName(e) || '-------',
                    numMessages: e.message_number ? e.message_number : 0,
                    numMessagesUnread: e.message_unread ? e.message_unread : 0,
                    photo: e.photo,
                    isNew: false,
                    isMine: true,
                    isOutbound: e.saliente ? e.saliente : false,
                    answered: false,
                    transferAgent: e.transfer_agent ? e.transfer_agent : null,
                    date: e.timestamp ? new Date(e.timestamp) : null,
                    expire: e.expire ? new Date(e.expire) : null,
                    errorEx: e.error_ex ? e.error_ex : null,
                    error: e.error ? e.error : false
                });
            }
        });
        state.agtInstagramChatsList = chats;
    },
    agtInstagramReceiveNewChat (state, chat = null) {
        if (!chat || !chat.chat_id) return;
        const from = chat && chat.from ? chat.from : null;
        const contactData = chat && chat.contact_data && chat.contact_data.nombre
            ? chat.contact_data.nombre
            : null;
        const chatData = {
            id: chat && chat.chat_id ? chat.chat_id : null,
            from: contactData || from,
            campaignId: getCampaignId(chat),
            campaignName: getCampaignName(chat) || '-------',
            numMessages:
                chat && chat.number_messages ? chat.number_messages : 1,
            numMessagesUnread:
                chat && chat.message_unread ? chat.message_unread : 1,
            photo: chat && chat.photo ? chat.photo : '',
            isNew: true,
            isMine: false,
            isOutbound: false,
            answered: false,
            transferAgent: chat && chat.transfer_agent ? chat.transfer_agent : null,
            date: chat && chat.timestamp ? new Date(chat.timestamp) : new Date(),
            expire: chat && chat.expire ? new Date(chat.expire) : null,
            errorEx: chat && chat.error_ex ? chat.error_ex : null,
            error: chat && chat.error ? chat.error : false
        };
        const chatIndex = state.agtInstagramChatsList.findIndex(
            (item) => item.id === chatData.id
        );
        if (chatIndex >= 0) {
            state.agtInstagramChatsList.splice(chatIndex, 1, {
                ...state.agtInstagramChatsList[chatIndex],
                ...chatData
            });
            return;
        }
        state.agtInstagramChatsList.push(chatData);
    },
    agtInstagramSetConversationInfo (state, conversation = null) {
        state.agtInstagramConversationInfo = {
            id: conversation && conversation.id ? conversation.id : null,
            campaignId: getCampaignId(conversation),
            campaignName: getCampaignName(conversation),
            ig_scoped_id:
                conversation && conversation.ig_scoped_id
                    ? conversation.ig_scoped_id
                    : null,
            client: setClientInfo(
                conversation && conversation.client ? conversation.client : null
            ),
            agent:
                conversation && conversation.agent ? conversation.agent : null,
            transferAgent:
                conversation && conversation.transferAgent
                    ? conversation.transferAgent
                    : null,
            isActive:
                conversation && conversation.isActive
                    ? conversation.isActive
                    : null,
            isDisposition:
                conversation && conversation.isDisposition
                    ? conversation.isDisposition
                    : null,
            expire:
                conversation && conversation.expire
                    ? conversation.expire
                    : null,
            timestamp:
                conversation && conversation.timestamp
                    ? conversation.timestamp
                    : null,
            messageNumber:
                conversation && conversation.messageNumber
                    ? conversation.messageNumber
                    : null,
            messageUnreadNumber:
                conversation && conversation.messageUnreadNumber
                    ? conversation.messageUnreadNumber
                    : null,
            photo:
                conversation && conversation.photo ? conversation.photo : null,
            page: setPageInfo(
                conversation && conversation.page ? conversation.page : null
            ),
            errorEx:
                conversation && conversation.errorEx ? conversation.errorEx : null,
            error:
                conversation && conversation.error ? conversation.error : false,
            isOutbound:
                conversation && conversation.isOutbound ? conversation.isOutbound : false
        };
    },
    agtInstagramRestartExpiredCoversation (state, info = null) {
        if (info) {
            state.agtInstagramConversationInfo.expire = info.expire;
            localStorage.setItem(
                'agtInstagramConversationInfo',
                JSON.stringify(state.agtInstagramConversationInfo)
            );
        }
    }
};
