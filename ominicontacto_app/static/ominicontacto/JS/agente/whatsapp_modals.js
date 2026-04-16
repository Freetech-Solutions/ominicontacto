const modalTransferChat = $('#whatsapp-modal-transfer-chat');
const modalTemplates = $('#whatsapp-modal-templates');
const modalDispositionForm = $('#whatsapp-modal-disposition-form');
const modalMediaImageForm = $('#whatsapp-modal-media-image-form');
const modalMediaFileForm = $('#whatsapp-modal-media-file-form');
const modalContactForm = $('#whatsapp-modal-contact-form');
const modalConversationNew = $('#whatsapp-modal-conversation-new');
const whatsappWrapper = $('#wrapperWhatsapp');
const lastConversationMessagesModal = $('#last-conversation-messages-modal');

const onWhatsappTransferChatEvent = ($event) => {
    const { transfer_chat } = $event.detail;
    modalTransferChat.modal(transfer_chat === true ? 'show' : 'hide');
};

const onWhatsappTemplatesEvent = ($event) => {
    const { templates, conversationId } = $event.detail;
    if (conversationId) {
        localStorage.setItem('agtWhatsappConversationId', conversationId);
    }
    modalTemplates.modal(templates === true ? 'show' : 'hide');
};

const onWhatsappDispositionFormEvent = ($event) => {
    const { disposition_form } = $event.detail;
    modalDispositionForm.modal(disposition_form === true ? 'show' : 'hide');
};

const onWhatsappMediaFormEvent = ($event) => {
    const { media_form, fileType } = $event.detail;
    if (media_form) {
        if (fileType === 'img') {
            modalMediaImageForm.modal('show');
        } else {
            modalMediaFileForm.modal('show');
        }
    } else {
        modalMediaFileForm.modal('hide');
        modalMediaImageForm.modal('hide');
    }
};

const onWhatsappContactFormEvent = ($event) => {
    const { contact_form } = $event.detail;
    modalContactForm.modal(contact_form === true ? 'show' : 'hide');
};

const onLastConversationMessagesEvent = ($event) => {
    
    const { last_conversation, conversationId } = $event.detail;

    console.log('modal event', conversationId);
    console.log('iframe reloaded');

    if (conversationId) {
        localStorage.setItem('agtWhatsLastConversationId', conversationId);
    }

    const iframe = document.querySelector('#last-conversation-messages-modal iframe');

    if (iframe && last_conversation === true) {
        const currentSrc = iframe.getAttribute('src');
        iframe.setAttribute('src', currentSrc);
    }

    lastConversationMessagesModal.modal(last_conversation === true ? 'show' : 'hide');
    lastConversationMessagesModal.on('shown.bs.modal', function () {
        const dialog = this.querySelector('.modal-dialog');
        const handle = this.querySelector('.drag-handle');

        let isDragging = false;
        let startX = 0;
        let startY = 0;
        let initialLeft = 0;
        let initialTop = 0;

        dialog.style.position = 'fixed';
        dialog.style.margin = '0';
        dialog.style.left = `${(window.innerWidth - dialog.offsetWidth) / 2}px`;
        dialog.style.top = `${(window.innerHeight - dialog.offsetHeight) / 2}px`;

        handle.onmousedown = (e) => {
            isDragging = true;
            startX = e.clientX;
            startY = e.clientY;
            initialLeft = dialog.offsetLeft;
            initialTop = dialog.offsetTop;

            document.onmousemove = (ev) => {
                if (!isDragging) return;

                dialog.style.left = `${initialLeft + (ev.clientX - startX)}px`;
                dialog.style.top = `${initialTop + (ev.clientY - startY)}px`;
            };

            document.onmouseup = () => {
                isDragging = false;
                document.onmousemove = null;
                document.onmouseup = null;
            };
        };
    });
};

const onWhatsappConversationNewEvent = ($event) => {
    const { conversation_new } = $event.detail;
    modalConversationNew.modal(conversation_new === true ? 'show' : 'hide');
};

const onWhatsappCloseContainerEvent = ($event) => {
    whatsappWrapper.addClass('hidden');
};

const setEventListeners = () => {
    window.document.addEventListener('onWhatsappCloseContainerEvent', onWhatsappCloseContainerEvent, false);
    window.document.addEventListener('onWhatsappTransferChatEvent', onWhatsappTransferChatEvent, false);
    window.document.addEventListener('onWhatsappTemplatesEvent', onWhatsappTemplatesEvent, false);
    window.document.addEventListener('onWhatsappDispositionFormEvent', onWhatsappDispositionFormEvent, false);
    window.document.addEventListener('onWhatsappMediaFormEvent', onWhatsappMediaFormEvent, false);
    window.document.addEventListener('onWhatsappContactFormEvent', onWhatsappContactFormEvent, false);
    window.document.addEventListener('onWhatsappConversationNewEvent', onWhatsappConversationNewEvent, false);
    window.document.addEventListener('onLastConversationMessagesEvent', onLastConversationMessagesEvent, false);
    $('#whatsappChat').on('click', function () {
        $('#wrapperWhatsapp').toggleClass('hidden');
        $('#wrapperFacebook').addClass('hidden');
        $('#wrapperWebphone').removeClass('active');
        $('#newChat').addClass('invisible');
    });
};

const setWhatsappStatusIcon = (tiene_whatsapp = false) => {
    $('#whatsappChat').css({ color: tiene_whatsapp ? '#52C159' : '#6A716A' });
};

$(function () {
    setEventListeners();
});
