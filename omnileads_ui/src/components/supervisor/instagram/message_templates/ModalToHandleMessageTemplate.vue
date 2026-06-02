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
    <Form @closeModalEvent="closeModal" :formToCreate="formToCreate" />
  </Dialog>
</template>

<script>
import { mapActions } from 'vuex';
import Form from '@/components/supervisor/instagram/message_templates/Form';

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
        Form
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
