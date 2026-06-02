<template>
  <div>
    <div class="card">
      <Steps :model="steps" />
    </div>
    <br />
    <br />
    <router-view
      class="mx-6"
      :formData="supInstagramAccount"
      @prev-page="prevAccount($event)"
      @next-page="nextAccount($event)"
    >
    </router-view>
  </div>
</template>

<script>
import { mapState } from 'vuex';

export default {
    props: {
        formToEdit: {
            type: Boolean,
            default: false
        },
        steps: {
            type: Array,
            default: () => []
        }
    },
    computed: {
        ...mapState(['supInstagramAccount'])
    },
    methods: {
        nextAccount (event) {
            this.$router.push(this.steps[event.pageIndex + 1].to);
        },
        prevAccount (event) {
            this.$router.push(this.steps[event.pageIndex - 1].to);
        }
    },
    watch: {
        steps: {
            handler () {},
            deep: true,
            immediate: true
        },
        supInstagramAccount: {
            handler () {},
            deep: true,
            immediate: true
        }
    }
};
</script>
