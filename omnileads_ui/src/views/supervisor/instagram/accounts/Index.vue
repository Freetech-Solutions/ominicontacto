<template>
  <div class="card">
    <Toolbar class="mb-4">
      <template #start>
        <h1>Cuentas Instagram</h1>
      </template>
      <template #end>
        <Button
          :label="$tc('globals.new')"
          icon="pi pi-plus"
          @click="newAccount"
        />
      </template>
    </Toolbar>
    <PagesTable />
  </div>
</template>

<script>
import { mapActions } from 'vuex';
import PagesTable from '@/components/supervisor/instagram/accounts/PagesTable';

export default {
    components: {
        PagesTable
    },
    async created () {
        await this.initInstagramAccounts();
    },
    methods: {
        newAccount () {
            this.initInstagramAccount({});
            this.$router.push({ name: 'supervisor_instagram_accounts_new_step1' });
        },
        ...mapActions(['initInstagramAccount', 'initInstagramAccounts'])
    }
};
</script>
