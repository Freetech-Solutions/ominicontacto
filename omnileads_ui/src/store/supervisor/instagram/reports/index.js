import {
    SupervisorInstagramCampaignReportActions,
    SupervisorInstagramCampaignReportMutations,
    SupervisorInstagramCampaignReportState
} from './campaign';

import SupervisorInstagramGeneralReportState from './general_report/state';
import SupervisorInstagramGeneralReportMutations from './general_report/mutations';
import SupervisorInstagramGeneralReportActions from './general_report/actions';

export const SupervisorInstagramReportState = {
    ...SupervisorInstagramCampaignReportState,
    ...SupervisorInstagramGeneralReportState
};

export const SupervisorInstagramReportMutations = {
    ...SupervisorInstagramCampaignReportMutations,
    ...SupervisorInstagramGeneralReportMutations
};

export const SupervisorInstagramReportActions = {
    ...SupervisorInstagramCampaignReportActions,
    ...SupervisorInstagramGeneralReportActions
};
