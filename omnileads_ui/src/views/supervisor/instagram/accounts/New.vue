<template>
  <div class="card">
    <Toolbar class="mb-4">
      <template #start>
        <h1>Nueva cuenta Instagram</h1>
      </template>
      <template #end>
        <Button
          :label="$tc('globals.back')"
          icon="pi pi-arrow-left"
          class="p-button-info mr-2"
          @click="back"
        />
      </template>
    </Toolbar>
    <FormSteps :steps="steps" />
  </div>
</template>

<script>
import { mapActions } from 'vuex';
import FormSteps from '@/components/supervisor/instagram/accounts/FormSteps';

export default {
    components: {
        FormSteps
    },
    data () {
        return {
            steps: [
                {
                    label: this.$t('views.facebook.page.step1.title'),
                    to: '/supervisor_instagram_accounts/new/step1'
                },
                {
                    label: this.$t('views.whatsapp.line.step2.title'),
                    to: '/supervisor_instagram_accounts/new/step2'
                },
                {
                    label: this.$t('views.whatsapp.line.step3.title'),
                    to: '/supervisor_instagram_accounts/new/step3'
                }
            ]
        };
    },
    async created () {
        await this.initInstagramAccountTemplates();
        await this.initGroupOfHours();
        await this.initInstagramAccountCampaigns();
        await this.initFormFlag(true);
    },
    methods: {
        ...mapActions(['initGroupOfHours', 'initFormFlag', 'initInstagramAccountTemplates', 'initInstagramAccountCampaigns']),
        back () {
            this.$router.push({ name: 'supervisor_instagram_accounts' });
        }
    }
};
</script>
