import { getConfigurationByType } from '@/helpers/supervisor/whatsapp/message_template';

export default {
    initInstagramAccountTemplates (state, messageTemplates) {
        state.supInstagramAccountTemplates = messageTemplates;
    },
    initInstagramAccountTemplate (state, messageTemplate = null) {
        if (messageTemplate) {
            state.supInstagramAccountTemplate = {
                id: messageTemplate.id,
                nombre: messageTemplate.nombre || messageTemplate.name,
                tipo: messageTemplate.tipo !== undefined ? messageTemplate.tipo : messageTemplate.type,
                configuracion: getConfigurationByType(
                    messageTemplate.tipo !== undefined ? messageTemplate.tipo : messageTemplate.type,
                    messageTemplate.configuracion || messageTemplate.configuration
                )
            };
        } else {
            state.supInstagramAccountTemplate = {
                id: null,
                nombre: '',
                tipo: null,
                configuracion: null
            };
        }
    },
    initInstagramAccountTemplateFormFields (state, { type = null, config = null }) {
        state.supInstagramAccountTemplateFormFields = getConfigurationByType(type === null ? 0 : type, config);
    }
};
