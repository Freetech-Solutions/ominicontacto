<script lang="ts">
import { reactiveOmit } from "@vueuse/core"
import type { AlertDialogActionProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import type { ButtonVariants } from "~shadcn/components/ui/button"
</script>

<script lang="ts" setup>
import { AlertDialogAction } from "reka-ui"
import { buttonVariants } from "~shadcn/components/ui/button"
import { cn } from "~shadcn/lib/utils"

const props = defineProps<
  AlertDialogActionProps & {
    class?: HTMLAttributes["class"]
    variant?: ButtonVariants["variant"]
  }
>()

const delegatedProps = reactiveOmit(props, "class")
</script>

<template>
  <AlertDialogAction v-bind="delegatedProps" v-bind:class="cn(buttonVariants({ variant }), props.class)">
    <slot />
  </AlertDialogAction>
</template>

<!-- + props.variant -->
