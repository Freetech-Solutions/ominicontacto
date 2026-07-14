<script lang="ts"></script>

<script lang="ts" setup>
onBeforeRouteUpdate((to) => {
  parent.postMessage({ id: "webui:inner-route-changed", path: to.fullPath })
})
</script>

<template lang="html">
  <div class="min-h-dvh bg-[#f4f6f8] p-4 dark:bg-[#2b2d31]">
    <router-view v-slot="{ Component }">
      <component v-bind:is="Component" />
    </router-view>
  </div>
</template>
