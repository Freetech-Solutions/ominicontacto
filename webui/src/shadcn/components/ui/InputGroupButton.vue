<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import type { ButtonVariants } from "~shadcn/components/ui/button"
import { Button } from "~shadcn/components/ui/button"
import type { InputGroupButtonVariants } from "~shadcn/components/ui/input-group"
import { inputGroupButtonVariants } from "~shadcn/components/ui/input-group"
import { cn } from "~shadcn/lib/utils"

interface InputGroupButtonProps {
  variant?: ButtonVariants["variant"]
  size?: InputGroupButtonVariants["size"]
  class?: HTMLAttributes["class"]
}

const props = withDefaults(defineProps<InputGroupButtonProps>(), {
  size: "xs",
  variant: "ghost",
})
</script>

<template>
  <Button
    type="button"
    v-bind:class="cn(inputGroupButtonVariants({ size: props.size }), props.class)"
    v-bind:data-size="props.size"
    v-bind:variant="props.variant">
    <slot />
  </Button>
</template>

<!-- + type="button" -->
