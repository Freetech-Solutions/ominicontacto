<template>
  <Dialog
    :visible="showModal"
    :style="{ width: '60vw' }"
    :closable="false"
    :modal="false"
  >
    <template #header>
      <h2>
        {{
          formToCreate
            ? "Nueva plantilla Instagram"
            : "Editar plantilla Instagram"
        }}
      </h2>
    </template>
    <Form
      @closeModalEvent="closeModal"
      :formToCreate="formToCreate"
      :return_after_save=return_after_save
    />
  </Dialog>
</template>

<script>
import { mapActions } from 'vuex';
import Form from '@/components/supervisor/instagram/message_templates/Form';
import { INSTAGRAM_URL_NAME } from '@/globals/supervisor/instagram';

export default {
    props: {
        showModal: {
            type: Boolean,
            default: false
        },
        formToCreate: {
            type: Boolean,
            default: true
        }
    },
    components: {
        Form,
        INSTAGRAM_URL_NAME
    },
    computed: {
        return_after_save() {
            return `${INSTAGRAM_URL_NAME}_accounts_new_step3`;
        }
    },
    methods: {
        ...mapActions(['initInstagramAccountTemplate']),
        closeModal () {
            this.$emit('handleModalEvent', {});
            this.initInstagramAccountTemplate({});
        }
    }
};
</script>
