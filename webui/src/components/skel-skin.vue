<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "~shadcn/lib/utils"

interface SkeletonProps {
  class?: HTMLAttributes["class"]
  active: boolean
}

const props = defineProps<SkeletonProps>()
</script>

<template>
  <span
    data-slot="skeleton"
    v-bind:class="
      cn(
        {
          'bg-primary/10 animate-pulse rounded-md text-transparent': props.active,
        },
        props.class,
      )
    ">
    <slot />
  </span>
</template>
