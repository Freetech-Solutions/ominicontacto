<script lang="ts">
import { useStorage } from "@vueuse/core"
</script>

<script lang="ts" setup>
import { Toaster, TooltipProvider } from "~/shadcn"

if (window.self !== window.top) {
  watch(
    useStorage("theme", "light"),
    (theme) => {
      if (theme === "light") {
        document.documentElement.classList.remove("dark")
      } else {
        document.documentElement.classList.add("dark")
      }
    },
    {
      immediate: true,
    },
  )
}
</script>

<template lang="html">
  <TooltipProvider v-bind:delay-duration="3_000">
    <router-view v-slot="{ Component }">
      <component v-bind:is="Component" />
    </router-view>
  </TooltipProvider>
  <Toaster close-button close-button-position="top-right" position="top-center" rich-colors theme="system" />
  <!-- <viewport-breakpoint /> -->
</template>
