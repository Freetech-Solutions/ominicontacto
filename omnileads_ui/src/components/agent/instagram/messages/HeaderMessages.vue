<template>
  <Toolbar class="mb-4" :style="{ border: `4px solid ${instagram_color}` }">
    <template #start>
      <i
        class="pi pi-instagram mr-2"
        :style="{ color: instagram_color, 'font-size': '3rem' }"
      ></i>
      <h2 class="font-bold">Instagram</h2>
    </template>
    <template #end>
      <Button
        icon="pi pi-times"
        class="p-button-danger"
        @click="close"
        v-tooltip.top="$t('globals.close')"
      />
    </template>
  </Toolbar>
</template>

<script>
import { COLORS } from '@/globals';
export default {
    data () {
        return {
            instagram_color: COLORS.INSTAGRAM.Pink
        };
    },
    methods: {
        close () {
            const event = new CustomEvent('onInstagramCloseContainerEvent', {
                detail: {
                    instagram_container: false
                }
            });
            window.parent.document.dispatchEvent(event);
        }
    }
};
</script>
