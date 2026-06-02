export default {
    agtInstagramContactListInit (state, contacts) {
        state.agtInstagramContactList = contacts;
    },
    agtInstagramContactDBFieldsInit (state, fields) {
        state.agtInstagramContactDBFields = fields;
    },
    agtInstagramContactSearchInit (state, contacts) {
        state.agtInstagramContactSearchResults = [];
        const contactsToAdd = [];
        for (const contact of contacts) {
            if (contact.id && !contactsToAdd.find(c => c.id === contact.id)) {
                contactsToAdd.push(contact);
            }
        }
        state.agtInstagramContactSearchResults = contactsToAdd;
    },
    agtInstagramNewContact (state, contact) {
        console.log('agtInstagramNewContact', contact);
        if (contact) {
            state.newContact = [];
            state.newContact.push(contact);
        }
    }
};
