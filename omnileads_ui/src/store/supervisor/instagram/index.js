import AccountsActions from './accounts/actions';
import AccountsMutations from './accounts/mutations';
import AccountsState from './accounts/state';
import MessageTemplateActions from './message_templates/actions';
import MessageTemplateMutations from './message_templates/mutations';
import MessageTemplateState from './message_templates/state';
import ConfigurationCampaignActions from './configuration_campaign/actions';
import ConfigurationCampaignMutations from './configuration_campaign/mutations';
import ConfigurationCampaignState from './configuration_campaign/state';

export const SupervisorInstagramState = {
    ...AccountsState,
    ...MessageTemplateState,
    ...ConfigurationCampaignState
};

export const SupervisorInstagramMutations = {
    ...AccountsMutations,
    ...MessageTemplateMutations,
    ...ConfigurationCampaignMutations
};

export const SupervisorInstagramActions = {
    ...AccountsActions,
    ...MessageTemplateActions,
    ...ConfigurationCampaignActions
};
