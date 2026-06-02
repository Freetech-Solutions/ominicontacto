export default {
    initInstagramAccounts(state, accounts) {
        state.supInstagramAccounts = accounts;
    },
    initInstagramAccount(state, page = null) {
        if (page) {
            state.supInstagramAccount = {
                id: page.id,
                name: page.name,
                description: page.description,
                access_token: page.access_token,
                verify_token: page.verify_token,
                app_id: page.app_id,
                page_id: page.page_id,
                ig_user_id: page.ig_user_id,
                username: page.username,
                destination: {
                    data: page.destination ? page.destination.data : null,
                    type: page.destination ? page.destination.type : null,
                    id_tmp: page.destination && page.destination.type === 14 ? page.destination.id : 0
                },
                schedule: page.horario,
                welcome_message: page.welcome_message,
                goodbye_message: page.goodbye_message,
                out_of_hours_message: page.out_of_hours_message
            };
            state.supInstagramAccountDestinationMenuOptions = page.destination ? page.destination.data : [];
        } else {
            state.supInstagramAccount = {
                id: null,
                name: '',
                description: '',
                access_token: null,
                verify_token: '',
                app_id: '',
                page_id: '',
                ig_user_id: '',
                username: '',
                destination: {
                    data: null,
                    type: null,
                    id_tmp: 0,
                    is_main: true
                },
                schedule: null,
                welcome_message: '',
                goodbye_message: '',
                out_of_hours_message: ''
            };
        }
    },
    initFormFlag(state, flag) {
        state.isFormToCreate = flag;
    },
    initInstagramAccountCampaigns(state, campaigns) {
        state.supInstagramAccountCampaigns = campaigns;
    },
    initInstagramAccountOptionForm(state, option = null) {
        state.supInstagramAccountOptionForm = {
            id: option ? option.id : null,
            index: option ? option.index : 0,
            value: option ? option.value : '',
            description: option ? option.description : '',
            type_option: option ? option.type_option : 0,
            destination: option ? option.destination : null
        };
    },
    createInstagramAccountOption(state, { data, menuId }) {
        const ultimoElemento = state.supInstagramAccountOptions[state.supInstagramAccountOptions.length - 1];
        const index = ultimoElemento ? ultimoElemento.index + 1 : 0;
        state.supInstagramAccountOptions.push({
            index: index,
            id: index,
            value: data.value,
            description: data.description,
            type_option: data.type_option,
            destination: data.destination,
            menuId: menuId
        });
    },
    updateInstagramAccountOption(state, { id, data, menuId }) {
        const destinationOptions = state.supInstagramAccount.destination.data.filter(item => item.id_tmp === menuId);
        const element = destinationOptions[0].options.find(item => item.id === id);
        if (element) {
            element.value = data.value;
            element.description = data.description;
            element.type_option = data.type_option;
            element.destination = data.destination;
        }
    },
    deleteInstagramAccountOption(state, { id, menuId }) {
        const destinationOptions = state.supInstagramAccount.destination.data.filter(item => item.id_tmp === menuId);
        destinationOptions[0].options = destinationOptions[0].options.filter(item => item.id !== id);
    }
};
