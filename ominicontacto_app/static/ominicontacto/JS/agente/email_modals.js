// Copyright (C) 2026 Freetech Solutions
//
// This file is part of OMniLeads
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Lesser General Public License version 3, as published by
// the Free Software Foundation.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Lesser General Public License for more details.
//
// You should have received a copy of the GNU Lesser General Public License
// along with this program.  If not, see http://www.gnu.org/licenses/.

// The email agent panel is a self-contained SPA (inbox + thread + reply +
// disposition/contact handled inline), so the parent console only needs to
// toggle the iframe wrapper and reflect the channel permission on the icon.
// There is intentionally NO transfer bridge.

const onEmailCloseContainerEvent = () => {
    $('#wrapperEmail').addClass('hidden').removeClass('reading');
    $('#emailReadingBackdrop').addClass('hidden');
};

// The email SPA (iframe) emits this on every websocket new-mail / new-reply so
// the bottom-bar icon mirrors WhatsApp: a red bell + an unread counter badge.
const onEmailNewMessageEvent = ($event) => {
    const count = $event && $event.detail ? $event.detail.count : 0;
    const $counter = $('#emailNotReadMessagesCounter');
    if (count > 0) {
        $('#newEmail').removeClass('invisible');
        $counter.text(count > 99 ? '99+' : count).removeClass('invisible');
    } else {
        $('#newEmail').addClass('invisible');
        $counter.text('').addClass('invisible');
    }
};

const clearEmailUnreadBadges = () => {
    $('#newEmail').addClass('invisible');
    $('#emailNotReadMessagesCounter').text('').addClass('invisible');
};

// When the agent opens/takes an email the SPA asks for a roomier reading area:
// promote the iframe wrapper to a large centered modal with a backdrop, and
// restore it to the inline inbox panel when the thread is closed.
// Ask the email SPA (inside the iframe) to go back to the inbox. Same-origin,
// so we can dispatch straight onto the iframe document; the SPA then restores
// the inline panel via onEmailReadingEvent(reading=false), keeping both in sync.
const requestEmailCloseThread = () => {
    const iframe = $('#wrapperEmail iframe')[0];
    if (iframe && iframe.contentWindow) {
        iframe.contentWindow.document.dispatchEvent(
            new CustomEvent('email:request_close_thread'));
    } else {
        onEmailReadingEvent({ detail: { reading: false } });
    }
};

const ensureEmailBackdrop = () => {
    if ($('#emailReadingBackdrop').length === 0) {
        $('<div id="emailReadingBackdrop"></div>')
            .on('click', requestEmailCloseThread)
            .appendTo('body');
    }
    return $('#emailReadingBackdrop');
};

const onEmailReadingEvent = ($event) => {
    const reading = $event && $event.detail ? $event.detail.reading : false;
    if (reading) {
        ensureEmailBackdrop().removeClass('hidden');
        $('#wrapperEmail').addClass('reading');
    } else {
        $('#wrapperEmail').removeClass('reading fullscreen');
        $('#emailReadingBackdrop').addClass('hidden');
    }
};

const onEmailFullscreenEvent = ($event) => {
    const fullscreen = $event && $event.detail ? $event.detail.fullscreen : false;
    $('#wrapperEmail').toggleClass('fullscreen', !!fullscreen);
};

const setEmailEventListeners = () => {
    window.document.addEventListener('onEmailCloseContainerEvent', onEmailCloseContainerEvent, false);
    window.document.addEventListener('onEmailNewMessageEvent', onEmailNewMessageEvent, false);
    window.document.addEventListener('onEmailReadingEvent', onEmailReadingEvent, false);
    window.document.addEventListener('onEmailFullscreenEvent', onEmailFullscreenEvent, false);
    $('#emailMessages').on('click', function () {
        $('#wrapperEmail').toggleClass('hidden');
        // toggling the panel always returns it to the inline (non-reading) state
        $('#wrapperEmail').removeClass('reading');
        $('#emailReadingBackdrop').addClass('hidden');
        $('#wrapperWhatsapp').addClass('hidden');
        $('#wrapperFacebook').addClass('hidden');
        $('#wrapperWebphone').removeClass('active');
        clearEmailUnreadBadges();
    });
};

const setEmailStatusIcon = (tiene_email = false) => {
    $('#emailMessages').css({ color: tiene_email ? '#52C159' : '#6A716A' });
};

$(function () {
    setEmailEventListeners();
});
