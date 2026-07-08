<script lang="ts"></script>

<script lang="ts" setup>
const { accountId } = defineProps<{ accountId: number }>()
</script>

<template lang="html">
  <router-view v-slot="{ Component }">
    <keep-alive include="list">
      <component :is="Component" />
    </keep-alive>
  </router-view>
</template>
