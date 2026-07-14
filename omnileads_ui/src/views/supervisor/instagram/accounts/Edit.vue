<template>
  <div class="card">
    <Toolbar class="mb-4">
      <template #start>
        <h1>Editar cuenta Instagram</h1>
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
    <FormSteps :formToEdit="true" :steps="steps" />
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
            steps: []
        };
    },
    async created () {
        const id = this.$route.params.id;
        await this.initInstagramAccount({ id });
        await this.initGroupOfHours();
        await this.initInstagramAccountCampaigns();
        await this.initInstagramAccountTemplates();
        await this.initFormFlag();
        this.steps = [
            {
                label: this.$t('views.facebook.page.step1.title'),
                to: `/supervisor_instagram_accounts/${id}/edit/step1`
            },
            {
                label: this.$t('views.facebook.page.step2.title'),
                to: `/supervisor_instagram_accounts/${id}/edit/step2`
            },
            {
                label: this.$t('views.facebook.page.step3.title'),
                to: `/supervisor_instagram_accounts/${id}/edit/step3`
            }
        ];
    },
    methods: {
        ...mapActions(['initGroupOfHours', 'initInstagramAccount', 'initFormFlag', 'initInstagramAccountCampaigns', 'initInstagramAccountTemplates']),
        back () {
            this.$router.push({ name: 'supervisor_instagram_accounts' });
        }
    }
};
</script>
