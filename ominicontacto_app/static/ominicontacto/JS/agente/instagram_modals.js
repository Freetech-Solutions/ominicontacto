const modalTransferChatInstagram = $('#instagram-modal-transfer-chat');
const modalTemplatesInstagram = $('#instagram-modal-templates');
const modalDispositionFormInstagram = $('#instagram-modal-disposition-form');
const modalMediaImageFormInstagram = $('#instagram-modal-media-image-form');
const modalMediaFileFormInstagram = $('#instagram-modal-media-file-form');
const modalContactFormInstagram = $('#instagram-modal-contact-form');
const modalConversationNewInstagram = $('#instagram-modal-conversation-new');
const instagramWrapper = $('#wrapperInstagram');
const metaChannelsWrapperInstagram = $('#wrapperMetaChannels');

const onInstagramTransferChatEvent = ($event) => {
    const { transfer_chat } = $event.detail;
    modalTransferChatInstagram.modal(transfer_chat === true ? 'show' : 'hide');
};

const onInstagramTemplatesEvent = ($event) => {
    const { templates, conversationId } = $event.detail;
    if (conversationId) {
        localStorage.setItem('agtInstagramConversationId', conversationId);
    }
    modalTemplatesInstagram.modal(templates === true ? 'show' : 'hide');
};

const onInstagramDispositionFormEvent = ($event) => {
    const { disposition_form } = $event.detail;
    modalDispositionFormInstagram.modal(disposition_form === true ? 'show' : 'hide');
};

const onInstagramMediaFormEvent = ($event) => {
    const { media_form, fileType } = $event.detail;
    if (media_form) {
        if (fileType === 'img') {
            modalMediaImageFormInstagram.modal('show');
        } else {
            modalMediaFileFormInstagram.modal('show');
        }
    } else {
        modalMediaFileFormInstagram.modal('hide');
        modalMediaImageFormInstagram.modal('hide');
    }
};

const onInstagramContactFormEvent = ($event) => {
    const { contact_form } = $event.detail;
    modalContactFormInstagram.modal(contact_form === true ? 'show' : 'hide');
};

const onInstagramConversationNewEvent = ($event) => {
    const { conversation_new } = $event.detail;
    modalConversationNewInstagram.modal(conversation_new === true ? 'show' : 'hide');
};

const onInstagramCloseContainerEvent = ($event) => {
    metaChannelsWrapperInstagram.addClass('hidden');
};

const setEventListenersInstagram = () => {
    window.document.addEventListener('onInstagramCloseContainerEvent', onInstagramCloseContainerEvent, false);
    window.document.addEventListener('onInstagramTransferChatEvent', onInstagramTransferChatEvent, false);
    window.document.addEventListener('onInstagramTemplatesEvent', onInstagramTemplatesEvent, false);
    window.document.addEventListener('onInstagramDispositionFormEvent', onInstagramDispositionFormEvent, false);
    window.document.addEventListener('onInstagramMediaFormEvent', onInstagramMediaFormEvent, false);
    window.document.addEventListener('onInstagramContactFormEvent', onInstagramContactFormEvent, false);
    window.document.addEventListener('onInstagramConversationNewEvent', onInstagramConversationNewEvent, false);
};

const setInstagramStatusIcon = (tiene_instagram = false) => {
    $('#facebookChat').css({ color: tiene_instagram ? '#52C159' : '#6A716A' });
};

$(function () {
    setEventListenersInstagram();
});
