<template>
  <div class="card">
    <div class="fluid grid formgrid mt-4">
      <div class="field col-6">
        <label
          :class="{
            'p-error':
              (v$.supInstagramAccount.name.$invalid && submitted) ||
              repeatedFormName,
          }"
          >{{ $t("models.facebook.page.name") }}*</label
        >
        <div class="p-inputgroup mt-2">
          <span class="p-inputgroup-addon">
            <i class="pi pi-list"></i>
          </span>
          <InputText
            :class="{
              'p-invalid':
                (v$.supInstagramAccount.name.$invalid && submitted) ||
                repeatedFormName,
            }"
            @input="validateFormName"
            :placeholder="$t('forms.form.enter_name')"
            v-model="v$.supInstagramAccount.name.$model"
          />
        </div>
        <small
          v-if="
            (v$.supInstagramAccount.name.$invalid && submitted) ||
            v$.supInstagramAccount.name.$pending.$response
          "
          class="p-error"
          >{{
            v$.supInstagramAccount.name.required.$message.replace(
              "Value",
              $t("models.facebook.page.name")
            )
          }}</small
        >
        <small v-if="repeatedFormName" class="p-error">{{
          $t("forms.form.validations.repeated_form_name")
        }}</small>
      </div>
      <div class="field col-6">
        <label
          :class="{
            'p-error': v$.supInstagramAccount.description.$invalid && submitted,
          }"
          >{{ $t("models.facebook.page.description") }}*</label
        >
        <div class="p-inputgroup mt-2">
          <span class="p-inputgroup-addon">
            <i class="pi pi-star"></i>
          </span>
          <Textarea
            :class="{
              'p-invalid':
                v$.supInstagramAccount.description.$invalid && submitted,
            }"
            :placeholder="$t('forms.form.enter_description')"
            v-model="v$.supInstagramAccount.description.$model"
          />
        </div>
        <small
          v-if="
            (v$.supInstagramAccount.description.$invalid && submitted) ||
            v$.supInstagramAccount.description.$pending.$response
          "
          class="p-error"
          >{{
            v$.supInstagramAccount.description.required.$message.replace(
              "Value",
              $t("models.facebook.page.description")
            )
          }}</small
        >
      </div>
    </div>
    <div class="flex justify-content-end flex-wrap">
      <div class="flex align-items-center justify-content-center">
        <Button
          :label="$t('globals.next')"
          icon="pi pi-angle-right"
          icon-pos="right"
          class="mt-4 p-button-secondary"
          @click="nextAccount(!v$.$invalid)"
        />
      </div>
    </div>
  </div>
</template>

<script>
import { mapState } from 'vuex';
import { useVuelidate } from '@vuelidate/core';
import { required } from '@vuelidate/validators';

export default {
    setup: () => ({ v$: useVuelidate() }),
    validations () {
        return {
            supInstagramAccount: {
                name: { required },
                description: { required }
            }
        };
    },
    inject: ['$helpers'],
    data () {
        return {
            submitted: false,
            repeatedFormName: false
        };
    },
    computed: {
        ...mapState(['supInstagramAccount', 'forms'])
    },
    methods: {
        validateFormName () {
            this.repeatedFormName =
        this.forms.find((f) => f.name === this.supInstagramAccount.name) !==
        undefined;
        },

        nextAccount (isFormValid) {
            this.submitted = true;
            if (isFormValid && !this.repeatedFormName) {
                this.$emit('next-page', { pageIndex: 0 });
            } else {
                return null;
            }
        }
    },
    watch: {
        forms: {
            handler () {},
            deep: true,
            immediate: true
        }
    }
};
</script>
