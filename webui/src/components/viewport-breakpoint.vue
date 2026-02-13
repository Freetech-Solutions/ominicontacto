<script lang="ts">
import { useWindowSize } from "@vueuse/core"

// oxfmt-ignore
const breackpoints = [
  {name:  "xs", class: "block   sm:hidden"          , cond:  "width < 40rem  (640px)"},
  {name:  "sm", class: "hidden  sm:block  md:hidden", cond: "width >= 40rem  (640px)"},
  {name:  "md", class: "hidden  md:block  lg:hidden", cond: "width >= 48rem  (768px)"},
  {name:  "lg", class: "hidden  lg:block  xl:hidden", cond: "width >= 64rem (1024px)"},
  {name:  "xl", class: "hidden  xl:block 2xl:hidden", cond: "width >= 80rem (1280px)"},
  {name: "2xl", class: "hidden 2xl:block"           , cond: "width >= 96rem (1536px)"},
]
</script>

<script lang="ts" setup>
const { width } = useWindowSize()
</script>

<template lang="html">
  <div class="fixed right-4 bottom-4 rounded border p-2 font-mono text-xs">
    <template v-for="bp in breackpoints" v-bind:key="bp.name">
      <div v-bind:class="bp.class">{{ bp.name }} {{ bp.cond }} {{ width }}px</div>
    </template>
  </div>
</template>
