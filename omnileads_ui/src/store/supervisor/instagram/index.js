import AccountsActions from './accounts/actions';
import AccountsMutations from './accounts/mutations';
import AccountsState from './accounts/state';
import MessageTemplateActions from './message_templates/actions';
import MessageTemplateMutations from './message_templates/mutations';
import MessageTemplateState from './message_templates/state';

export const SupervisorInstagramState = {
    ...AccountsState,
    ...MessageTemplateState
};

export const SupervisorInstagramMutations = {
    ...AccountsMutations,
    ...MessageTemplateMutations
};

export const SupervisorInstagramActions = {
    ...AccountsActions,
    ...MessageTemplateActions
};
