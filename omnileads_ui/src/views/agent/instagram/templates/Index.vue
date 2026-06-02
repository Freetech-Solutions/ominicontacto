<template>
  <div>
    <Header @handleClearFiltersEvent="clearFiltersEvent" />
    <Table
      ref="tableRef"
      @handleModalEvent="handleModal"
      :onlyInstagramTemplates="onlyInstagramTemplates"
    />
    <ModalTemplateParams
      :showModal="showModal"
      :template="template"
      :conversationId="conversationId"
      :onlyInstagramTemplates="onlyInstagramTemplates"
      @handleModalEvent="handleModal"
    />
  </div>
</template>

<script>
import Header from '@/components/agent/instagram/templates/Header';
import Table from '@/components/agent/instagram/templates/Table';
import ModalTemplateParams from '@/components/agent/instagram/templates/ModalTemplateParams';
import { INSTAGRAM_LOCALSTORAGE_EVENTS } from '@/globals/agent/instagram';
import { mapActions, mapState } from 'vuex';
import { HTTP_STATUS } from '@/globals';
export default {
    inject: ['$helpers'],
    components: {
        Header,
        Table,
        ModalTemplateParams
    },
    data () {
        return {
            showModal: false,
            template: null,
            conversationId: null,
            campaignId: null,
            conversationInfo: null,
            onlyInstagramTemplates: false
        };
    },
    async created () {
        await this.updatedLocalStorage();
    },
    mounted () {
        window.parent.document.addEventListener(
            INSTAGRAM_LOCALSTORAGE_EVENTS.TEMPLATES_INIT_EVENT,
            this.updatedLocalStorage
        );
        window.parent.document.addEventListener(
            INSTAGRAM_LOCALSTORAGE_EVENTS.CONVERSATION.RESTART_EXPIRED_CHAT,
            this.updatedLocalStorage
        );
    },
    beforeUnmount () {
        window.parent.document.removeEventListener(
            INSTAGRAM_LOCALSTORAGE_EVENTS.TEMPLATES_INIT_EVENT,
            this.updatedLocalStorage
        );
        window.parent.document.removeEventListener(
            INSTAGRAM_LOCALSTORAGE_EVENTS.CONVERSATION.RESTART_EXPIRED_CHAT,
            this.updatedLocalStorage
        );
    },
    computed: {
        ...mapState(['agtInstagramConversationInfo'])
    },
    methods: {
        ...mapActions(['initSupCampaignInstagramTemplates', 'agtInstagramSetConversationInfo']),
        clearFiltersEvent () {
            this.$refs.tableRef.clearFilter();
        },
        handleModal ({ showModal = false, template = null, conversationId = null }) {
            this.showModal = showModal;
            this.template = template;
            this.conversationId = conversationId;
        },
        async updatedLocalStorage () {
            this.conversationInfo =
        JSON.parse(localStorage.getItem('agtInstagramConversationInfo')) || null;
            this.onlyInstagramTemplates =
        localStorage.getItem('onlyInstagramTemplates')?.toString() === 'true';
            this.agtInstagramSetConversationInfo(this.conversationInfo);
            this.conversationId = this.conversationInfo?.id
                ? parseInt(this.conversationInfo?.id)
                : null;
            this.campaignId = this.conversationInfo?.campaignId
                ? parseInt(this.conversationInfo?.campaignId)
                : null;
            const page = this.conversationInfo?.page || null;
            if (this.campaignId) {
                console.log('Cargando plantillas para la campaña:', this.campaignId);
                this.$helpers.openLoader(this.$t);
                const { status, message } = await this.initSupCampaignInstagramTemplates({
                    campaignId: this.campaignId,
                    pageId: page ? page.id : null
                });
                this.$helpers.closeLoader();
                if (status !== HTTP_STATUS.SUCCESS) {
                    this.$swal(
                        this.$helpers.getToasConfig(
                            this.$t('globals.error_notification'),
                            message,
                            this.$t('globals.icon_error')
                        )
                    );
                }
            }
        }
    }
};
</script>
