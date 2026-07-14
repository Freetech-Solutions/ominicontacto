<template>
  <Dialog
    v-model:visible="showModal"
    :style="{ width: '70vw' }"
    modal
    :closable="false"
  >
    <template #header>
      <h2>
        {{ $t("views.group_of_hour.new_title") }}
      </h2>
    </template>
    <Form
      @closeModalEvent="closeModal"
      :formToCreate="true"
      :return_after_save=return_after_save
    />
  </Dialog>
</template>

<script>
import Form from '@/components/supervisor/group_of_hours/Form';
import { INSTAGRAM_URL_NAME } from '@/globals/supervisor/instagram';
export default {
    props: {
        showModal: {
            type: Boolean,
            default: false
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
        closeModal (response) {
            this.$emit('handleModalEvent', { showModal: false });
        }
    }
};
</script>
