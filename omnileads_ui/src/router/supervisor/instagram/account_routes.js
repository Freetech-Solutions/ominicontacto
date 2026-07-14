import Index from '@/views/supervisor/instagram/accounts/Index';
import New from '@/views/supervisor/instagram/accounts/New';
import Edit from '@/views/supervisor/instagram/accounts/Edit';
import Step1 from '@/components/supervisor/instagram/accounts/form_steps/Step1';
import Step2 from '@/components/supervisor/instagram/accounts/form_steps/Step2';
import Step3 from '@/components/supervisor/instagram/accounts/form_steps/Step3';
import { INSTAGRAM_URL_NAME } from '@/globals/supervisor/instagram';

export default [
    {
        path: `/${INSTAGRAM_URL_NAME}_accounts.html`,
        name: `${INSTAGRAM_URL_NAME}_accounts`,
        component: Index
    },
    {
        path: `/${INSTAGRAM_URL_NAME}_accounts/new`,
        name: `${INSTAGRAM_URL_NAME}_accounts_new`,
        component: New,
        children: [
            {
                path: 'step1',
                name: `${INSTAGRAM_URL_NAME}_accounts_new_step1`,
                component: Step1
            },
            {
                path: 'step2',
                name: `${INSTAGRAM_URL_NAME}_accounts_new_step2`,
                component: Step2
            },
            {
                path: 'step3',
                name: `${INSTAGRAM_URL_NAME}_accounts_new_step3`,
                component: Step3
            }
        ]
    },
    {
        path: `/${INSTAGRAM_URL_NAME}_accounts/:id/edit`,
        name: `${INSTAGRAM_URL_NAME}_accounts_edit`,
        component: Edit,
        children: [
            {
                path: 'step1',
                name: `${INSTAGRAM_URL_NAME}_accounts_edit_step1`,
                component: Step1
            },
            {
                path: 'step2',
                name: `${INSTAGRAM_URL_NAME}_accounts_edit_step2`,
                component: Step2
            },
            {
                path: 'step3',
                name: `${INSTAGRAM_URL_NAME}_accounts_edit_step3`,
                component: Step3
            }
        ]
    }
];
