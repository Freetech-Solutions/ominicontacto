// Realtime consumer for the agent email channel. Connects to the Django
// Channels group `agent-console-email` and re-emits backend events as window
// CustomEvents so the email SPA can refresh the inbox without polling.
const MAX_RECONNECT_ATTEMPTS = 5;
const TIME_TO_RETRY = 15; // segs

export const EMAIL_EVENTS = {
    NEW_CONVERSATION: 'email_new_conversation',
    NEW_MESSAGE: 'email_new_message',
    CONVERSATION_ATTENDED: 'email_conversation_attended'
};

export class EmailConsumer {
    static #instance = null;

    constructor (url = `wss://${window.location.host}/channels/agent-console-email`) {
        this.url = url;
        this.reconnectIntent = 0;
        this.consumer = null;
        this.open();
    }

    static getInstance ({ url = `wss://${window.location.host}/channels/agent-console-email` } = {}) {
        if (!EmailConsumer.#instance) {
            EmailConsumer.#instance = new EmailConsumer(url);
        }
        return EmailConsumer.#instance;
    }

    isConnected () {
        return this.consumer && this.consumer.readyState === WebSocket.OPEN;
    }

    open () {
        try {
            this.consumer = new WebSocket(this.url);
            this.consumer.onopen = () => {
                this.reconnectIntent = 0;
                console.log('Email Consumer OPEN: connection established');
            };
            this.consumer.onmessage = (event) => this.onMessage(event);
            this.consumer.onclose = (event) => {
                if (!event?.wasClean) this.retry();
            };
            this.consumer.onerror = () => this.consumer && this.consumer.close();
        } catch (error) {
            console.error('Email Consumer: could not open the socket', error);
            this.retry();
        }
    }

    retry () {
        if (this.reconnectIntent >= MAX_RECONNECT_ATTEMPTS) {
            console.error('Email Consumer: max reconnect attempts reached');
            return;
        }
        this.reconnectIntent += 1;
        setTimeout(() => this.open(), TIME_TO_RETRY * 1000);
    }

    onMessage (event) {
        let payload;
        try {
            payload = JSON.parse(event.data);
        } catch (error) {
            return;
        }
        const { type, args } = payload || {};
        if (!type) return;
        // Re-emit as a window event: e.g. 'email:email_new_conversation'.
        window.document.dispatchEvent(
            new CustomEvent(`email:${type}`, { detail: args })
        );
    }

    close () {
        if (this.consumer) {
            this.consumer.close();
            this.consumer = null;
        }
    }
}
