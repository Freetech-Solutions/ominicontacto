<template>
  <div class="card">
    <DataTable
      :value="accounts"
      class="p-datatable-sm"
      showGridlines
      :scrollable="true"
      scrollHeight="600px"
      responsiveLayout="scroll"
      dataKey="id"
      :rows="10"
      :rowsPerPageOptions="[10, 20, 50]"
      :paginator="true"
      paginatorTemplate="CurrentPageReport FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink RowsPerPageDropdown"
      :currentPageReportTemplate="
        $t('globals.showing_datatable_info', {
          first: '{first}',
          last: '{last}',
          totalRecords: '{totalRecords}',
        })
      "
      :filters="filters"
      :globalFilterFields="['name', 'username', 'app_id', 'page_id', 'ig_user_id']"
    >
      <template #header>
        <div class="flex justify-content-between flex-wrap">
          <div class="flex align-items-center justify-content-center">
            <Button
              type="button"
              icon="pi pi-filter-slash"
              :label="$t('globals.clean_filter')"
              class="p-button-outlined"
              @click="clearFilter()"
            />
          </div>
          <div class="flex align-items-center justify-content-center">
            <span class="p-input-icon-left">
              <i class="pi pi-search" />
              <InputText
                v-model="filters['global'].value"
                icon="pi pi-check"
                :placeholder="
                  $t('globals.find_by', { field: $tc('globals.name', 1) })
                "
              />
            </span>
          </div>
        </div>
      </template>
      <template #empty> {{ $t("globals.without_data") }} </template>
      <template #loading> {{ $t("globals.load_info") }} </template>
      <Column
        field="name"
        :header="$t('models.facebook.page.name')"
        :sortable="true"
      ></Column>
      <Column
        field="username"
        header="Usuario"
      ></Column>
      <Column
        field="app_id"
        header="App ID"
      ></Column>
      <Column
        field="page_id"
        header="Page ID"
      ></Column>
      <Column
        field="ig_user_id"
        header="Instagram User ID"
      ></Column>
      <Column :header="$tc('globals.option', 2)" style="max-width: 20rem">
        <template #body="slotProps">
          <Button
            icon="pi pi-pencil"
            class="p-button-warning ml-2"
            @click="edit(slotProps.data)"
            v-tooltip.top="$t('globals.edit')"
          />
          <Button
            icon="pi pi-trash"
            class="p-button-danger ml-2"
            @click="remove(slotProps.data.id)"
            v-tooltip.top="$t('globals.delete')"
          />
        </template>
      </Column>
    </DataTable>
  </div>
</template>

<script>
import { mapActions, mapState } from 'vuex';
import { FilterMatchMode } from 'primevue/api';
import { HTTP_STATUS, CONFIRM_BTN_COLOR, CANCEL_BTN_COLOR } from '@/globals';

export default {
    inject: ['$helpers'],
    data () {
        return {
            filters: null,
            accounts: []
        };
    },
    created () {
        this.initFilters();
    },
    computed: {
        ...mapState(['supInstagramAccounts'])
    },
    methods: {
        clearFilter () {
            this.initFilters();
        },
        initFilters () {
            this.filters = {
                global: { value: null, matchMode: FilterMatchMode.CONTAINS }
            };
        },
        edit (page) {
            this.$router.push({
                name: 'supervisor_instagram_accounts_edit_step1',
                params: { id: page.id }
            });
        },
        getSeverity (page) {
            switch (page.status) {
            case 'LIVE':
                return 'success';
            default:
                return null;
            }
        },
        async remove (id) {
            this.$swal({
                title: this.$t('globals.sure_notification'),
                icon: this.$t('globals.icon_warning'),
                showCancelButton: true,
                confirmButtonText: this.$t('globals.yes'),
                cancelButtonText: this.$t('globals.no'),
                confirmButtonColor: CONFIRM_BTN_COLOR,
                cancelButtonColor: CANCEL_BTN_COLOR,
                backdrop: false,
                reverseButtons: true
            }).then(async (result) => {
                if (result.isConfirmed) {
                    this.$swal.fire({
                        title: this.$t('globals.processing_request'),
                        timerProgressBar: true,
                        allowOutsideClick: false,
                        didOpen: () => {
                            this.$swal.showLoading();
                        }
                    });
                    const { status, message } = await this.deleteInstagramAccount(id);
                    this.$swal.close();
                    if (status === HTTP_STATUS.SUCCESS) {
                        this.initInstagramAccounts();
                        this.$swal(
                            this.$helpers.getToasConfig(
                                this.$t('globals.success_notification'),
                                message,
                                this.$t('globals.icon_success')
                            )
                        );
                    } else {
                        this.$swal(
                            this.$helpers.getToasConfig(
                                this.$t('globals.error_notification'),
                                message,
                                this.$t('globals.icon_error')
                            )
                        );
                    }
                }
            });
        },
        ...mapActions([
            'deleteInstagramAccount',
            'initInstagramAccounts',
            'initInstagramAccount'
        ])
    },
    watch: {
        supInstagramAccounts: {
            handler () {
                this.accounts = this.supInstagramAccounts.map((page) => {
                    return {
                        id: page.id,
                        name: page.name,
                        description: page.description,
                        access_token: page.access_token,
                        verify_token: page.verify_token,
                        app_id: page.app_id,
                        page_id: page.page_id,
                        destination: page.destination,
                        horario: page.horario,
                        ig_user_id: page.ig_user_id,
                        username: page.username,
                        mensaje_bienvenida: page.welcome_message,
                        mensaje_despedida: page.goodbye_message,
                        mensaje_fueradehora: page.out_of_hours_message
                    };
                });
            },
            deep: true,
            immediate: true
        }
    }
};
</script>
