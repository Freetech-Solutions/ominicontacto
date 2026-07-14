export const INSTAGRAM_URL_NAME = 'agent_instagram';
export const notificationEvent = (title, text, icon) => {
    const event = new CustomEvent('onInstagramNotificationEvent', {
        detail: { title, text, icon }
    });
    window.parent.document.dispatchEvent(event);
};
export const INSTAGRAM_MESSAGE = {
    SENDERS: {
        AGENT: 0,
        CLIENT: 1
    },
    STATUS: {
        SENT: 'sent',
        DELIVERED: 'delivered',
        READ: 'read',
        ERROR: 'failed'
    }
};
export const NOTIFICATION = {
    ICONS: {
        SUCCESS: 'SUCCESS',
        ERROR: 'ERROR',
        WARNING: 'WARNING',
        INFO: 'INFO'
    },
    TITLES: {
        SUCCESS: 'SUCCESS',
        ERROR: 'ERROR',
        WARNING: 'WARNING',
        INSTAGRAM_NEW_CHAT: null,
        INSTAGRAM_CHAT_ATTENDED: 'INSTAGRAM_CHAT_ATTENDED',
        INSTAGRAM_CHAT_TRANSFERED: 'INSTAGRAM_CHAT_TRANSFERED',
        INSTAGRAM_NEW_MESSAGE: null,
        INSTAGRAM_MESSAGE_STATUS: null,
        INSTAGRAM_CHAT_EXPIRED: 'INSTAGRAM_CHAT_EXPIRED'
    }
};
export const INSTAGRAM_EVENTS = {
    NEW_CHAT: 'instagram_new_chat',
    CHAT_ATTENDED: 'instagram_chat_attended',
    CHAT_TRANSFERED: 'instagram_chat_transfered',
    NEW_MESSAGE: 'instagram_new_message',
    MESSAGE_STATUS: 'instagram_message_status',
    CHAT_EXPIRED: 'instagram_chat_expired'
};
export const INSTAGRAM_LOCALSTORAGE_EVENTS = {
    TEMPLATES_INIT_EVENT: 'instagram-localstorage-templates-init-data-event',
    CONVERSATION: {
        NEW_INIT_DATA: 'instagram-localstorage-conversation-new-init-data-event',
        DETAIL_INIT_DATA: 'instagram-localstorage-conversation-detail-init-data-event',
        RESTART_EXPIRED_CHAT: 'instagram-localstorage-conversation-restart-expired-chat-init-data-event'
    },
    CONTACT: {
        FORM_INIT_DATA: 'instagram-localstorage-contact-form-init-data-event'
    },
    DISPOSITION: {
        FORM_INIT_DATA: 'instagram-localstorage-disposition-form-init-data-event',
        DONE: 'instagram-localstorage-disposition-done-event'
    },
    TRANSFER: {
        DONE: 'instagram-localstorage--transfer--done',
        FORM_INIT_DATA: 'instagram-localstorage-transfer-form-init-data-event'
    }
};
