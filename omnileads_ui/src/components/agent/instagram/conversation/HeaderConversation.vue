<template>
  <Toolbar>
    <template #start>
      <div class="flex flex-column gap-2">
        <div class="flex align-items-center">
          <Button
            v-if="!viewAsReport"
            @click="back"
            v-tooltip.top="$t('globals.back')"
            icon="pi pi-arrow-left"
            class="p-button-rounded p-button-secondary p-button-text"
          />
          <Chip
            :label="clientInfo?.name  + ' (' + clientInfo?.ig_scoped_id + ')'"
            icon="pi pi-user"
          />
        </div>
        <Tag
          v-if="agtInstagramConversationInfo.transferAgent"
          icon="pi pi-user-plus"
          :value="`Transferido por ${agtInstagramConversationInfo.transferAgent}`"
          severity="secondary"
          rounded
        />
      </div>
    </template>
    <template #end>
      <div v-if="!viewAsReport">
        <SplitButton
          v-if="!isExpired"
          icon="pi pi-paperclip"
          :model="attachOptions"
          :disabled="areConversationActionsDisabled"
          v-tooltip.top="$t('globals.attach')"
          class="p-button-warning"
        />
        <Button
          v-if="!isExpired"
          icon="pi pi-arrows-h"
          class="p-button-secondary ml-2"
          :disabled="areConversationActionsDisabled"
          @click="transfer"
          v-tooltip.top="$t('globals.transfer')"
        />
        <Button
          v-if="agtInstagramConversationInfo.client.id"
          icon="pi pi-save"
          class="ml-2"
          :disabled="areConversationActionsDisabled"
          @click="qualify"
          v-tooltip.top="$t('globals.save')"
        />
        <Button
          v-if="!isExpired"
          icon="pi pi-copy"
          class="p-button-info ml-2"
          :disabled="areConversationActionsDisabled"
          @click="templates"
          v-tooltip.top="$tc('globals.whatsapp.template', 2)"
        />
        <Button
          v-if="agtInstagramConversationInfo.client.id"
          icon="pi pi-user-edit"
          class="p-button-secondary ml-2"
          @click="editUserInfo"
          v-tooltip.top="$t('views.whatsapp.contact.settings.edit_info')"
        />
        <Button
          icon="pi pi-times"
          @click="close"
          class="p-button-danger ml-2"
          v-tooltip.top="$t('globals.close')"
        />
      </div>
    </template>
  </Toolbar>

</template>

<script>
import { mapActions, mapState } from 'vuex';
import { INSTAGRAM_LOCALSTORAGE_EVENTS } from '@/globals/agent/instagram';

export default {
    inject: ['$helpers'],
    props: {
        isExpired: {
            type: Boolean,
            default: false
        },
        viewAsReport: {
            type: Boolean,
            default: false
        }
    },
    data () {
        return {
            attachOptions: [
                {
                    label: this.$tc('globals.media.image', 2),
                    icon: 'pi pi-image',
                    command: () => {
                        this.attach();
                    }
                },
                {
                    label: this.$tc('globals.media.doc', 2),
                    icon: 'pi pi-file-pdf',
                    command: () => {
                        this.attach('pdf');
                    }
                }
            ],
            settingOptions: [
                {
                    label: this.$t('views.whatsapp.contact.settings.edit_info'),
                    icon: 'pi pi-user-edit',
                    command: () => {
                        this.editUserInfo();
                    }
                },
                {
                    label: this.$t('views.whatsapp.contact.settings.show_info'),
                    icon: 'pi pi-info-circle',
                    command: () => {
                        this.showUserInfo();
                    }
                }
            ],
            conversationId: null,
            clientInfo: {
                name: '',
                ig_scoped_id: '',
                avatar:
          'https://www.primefaces.org/wp-content/uploads/2020/05/placeholder.png'
            }
        };
    },
    computed: {
        ...mapState(['agtInstagramConversationInfo', 'agtInstagramConversationMessages']),
        areConversationActionsDisabled () {
            return Boolean(this.agtInstagramConversationInfo?.isDisposition);
        }
    },
    methods: {
        ...mapActions(['agtInstagramSetConversationMessages']),
        back () {
            this.$router.push({ name: 'agent_instagram' });
        },
        templates () {
            localStorage.setItem(
                'agtInstagramConversationMessages',
                JSON.stringify(this.agtInstagramConversationMessages)
            );
            localStorage.setItem(
                'agtInstagramConversationInfo',
                JSON.stringify(this.agtInstagramConversationInfo)
            );
            localStorage.setItem('onlyInstagramTemplates', false);
            const event = new Event(
                INSTAGRAM_LOCALSTORAGE_EVENTS.TEMPLATES_INIT_EVENT
            );
            window.parent.document.dispatchEvent(event);
            const modalEvent = new CustomEvent('onInstagramTemplatesEvent', {
                detail: {
                    templates: true,
                    conversationId: parseInt(this.$route.params.id)
                }
            });
            window.parent.document.dispatchEvent(modalEvent);
        },
        attach (fileType = 'img') {
            localStorage.setItem(
                'agtInstagramConversationMessages',
                JSON.stringify(this.agtInstagramConversationMessages)
            );
            localStorage.setItem(
                'agtInstagramConversationInfo',
                JSON.stringify(this.agtInstagramConversationInfo)
            );
            const event = new CustomEvent('onInstagramMediaFormEvent', {
                detail: {
                    media_form: true,
                    fileType: fileType
                }
            });
            window.parent.document.dispatchEvent(event);
        },
        showUserInfo () {
            const event = new CustomEvent('onInstagramUserInfoEvent', {
                detail: {
                    user_info: true
                }
            });
            window.parent.document.dispatchEvent(event);
        },
        editUserInfo () {
            localStorage.setItem('agtInstagramInconmingConversation', false);
            localStorage.setItem(
                'agtInstagramConversationInfo',
                JSON.stringify(this.agtInstagramConversationInfo)
            );
            const event = new Event(
                INSTAGRAM_LOCALSTORAGE_EVENTS.CONTACT.FORM_INIT_DATA
            );
            const modalEvent = new CustomEvent('onInstagramContactFormEvent', {
                detail: {
                    contact_form: true
                }
            });
            window.parent.document.dispatchEvent(event);
            window.parent.document.dispatchEvent(modalEvent);
        },
        qualify () {
            localStorage.setItem(
                'agtInstagramConversationInfo',
                JSON.stringify(this.agtInstagramConversationInfo)
            );
            localStorage.setItem(
                'agtInstagramDispositionChatFormToCreate',
                !this.agtInstagramConversationInfo.isDisposition
            );
            const event = new Event(
                INSTAGRAM_LOCALSTORAGE_EVENTS.DISPOSITION.FORM_INIT_DATA
            );
            window.parent.document.dispatchEvent(event);
            const modalEvent = new CustomEvent('onInstagramDispositionFormEvent', {
                detail: {
                    disposition_form: true
                }
            });
            window.parent.document.dispatchEvent(modalEvent);
        },
        transfer () {
            localStorage.setItem(
                'agtInstagramConversationInfo',
                JSON.stringify(this.agtInstagramConversationInfo)
            );
            const event = new Event(
                INSTAGRAM_LOCALSTORAGE_EVENTS.TRANSFER.FORM_INIT_DATA
            );
            window.parent.document.dispatchEvent(event);
            const modalEvent = new CustomEvent('onInstagramTransferChatEvent', {
                detail: {
                    transfer_chat: true
                }
            });
            window.parent.document.dispatchEvent(modalEvent);
        },
        close () {
            const event = new CustomEvent('onInstagramCloseContainerEvent', {
                detail: {
                    instagram_container: false
                }
            });
            window.parent.document.dispatchEvent(event);
        }
    },
    watch: {
        agtInstagramConversationInfo: {
            handler () {
                if (this.agtInstagramConversationInfo) {
                    if (this.agtInstagramConversationInfo.client.id) {
                        this.clientInfo.name = this.agtInstagramConversationInfo.client.data.nombre || this.agtInstagramConversationInfo.client.data.name || '';
                        this.clientInfo.ig_scoped_id = this.agtInstagramConversationInfo.client.ig_scoped_id;
                    } else {
                        this.clientInfo.name = this.agtInstagramConversationInfo.client_alias || '';
                        this.clientInfo.ig_scoped_id = this.agtInstagramConversationInfo.ig_scoped_id;
                    }
                }
            },
            deep: true,
            immediate: true
        },
        agtInstagramConversationMessages: {
            handler () {
                console.log('agtInstagramConversationMessages changed');
            },
            deep: true,
            immediate: true
        },
        isExpired: {
            handler () {},
            deep: true,
            immediate: true
        },
        viewAsReport: {
            handler () {},
            deep: true,
            immediate: true
        }
    }
};
</script>
