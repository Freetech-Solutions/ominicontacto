<script lang="ts">
import { useQuery } from "@pinia/colada"
import { mande, type MandeError } from "mande"

type Message = {
  id: number
  date: string
  subject: string
  from_mail: string
  to_mail: string
}

type PaginatedResponse = {
  per_page: number
  total: number
  page: number
  results: Message[]
}
</script>

<script lang="ts" setup>
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Input,
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
  ScrollArea,
  Skeleton,
} from "~/shadcn"

const { accountId } = defineProps<{ accountId: number }>()

const api = mande("/email/api/v1/accounts")
const route = useRoute()
const router = useRouter()

const list = useQuery<PaginatedResponse, MandeError<any>, undefined>({
  key: () => ["email-accounts", accountId, "messages", "?page", Number(route.query.page) || 1],
  placeholderData: (previousData) => previousData,
  query() {
    return api.get<PaginatedResponse>(`${accountId}/messages?page=${Number(route.query.page) || 1}`)
  },
})

function handleRefetch() {
  if (!list.isLoading.value) {
    list.refetch(true)
  }
}

function handlePageUpdate(page: number) {
  router.push({ name: "embed:email:account:message:list", query: { page } })
}
</script>

<template lang="html">
  <Card>
    <div class="grid grid-cols-[auto_1fr] gap-2 px-6">
      <Button class="rounded-full" variant="secondary" size="icon-lg" as-child>
        <router-link v-bind:to="{ name: 'embed:email:account:list' }">
          <i-hugeicons-arrow-left-01 class="size-8" />
        </router-link>
      </Button>
      <CardHeader class="px-0">
        <CardTitle>
          {{ "Account Messages" }}
        </CardTitle>
        <CardDescription>
          {{ "You can view all messages related to account" }}
        </CardDescription>
        <CardAction class="flex gap-2">
          <Input class="h-10" placeholder="Search... (tbd)" />
          <Button size="icon-lg" variant="outline" v-on:click="handleRefetch">
            <i-hugeicons-repost class="size-6" />
          </Button>
        </CardAction>
      </CardHeader>
    </div>
    <CardContent>
      <template v-if="list.status.value === 'error'">
        <Alert variant="destructive">
          <i-hugeicons-alert-circle />
          <AlertTitle>
            {{ "Unable to retrieve the list of messages" }}
          </AlertTitle>
          <AlertDescription v-if="list.error.value">
            <p>{{ list.error.value.body?.detail || list.error.value.toString() }}</p>
          </AlertDescription>
        </Alert>
      </template>
      <template v-else-if="list.status.value === 'success'">
        <template v-if="list.data.value?.results.length">
          <ScrollArea class="-mx-4 max-h-[calc(100vh-200px)] overflow-auto">
            <div class="px-4 pb-2">
              <ItemGroup class="gap-3 px-4 pb-2">
                <Item variant="outline" v-for="message in list.data.value.results" v-bind:key="message.id">
                  <ItemContent>
                    <ItemDescription>
                      <skel-skin v-bind:active="list.isLoading.value">
                        {{ message.date }}
                      </skel-skin>
                    </ItemDescription>
                    <ItemDescription>
                      <skel-skin v-bind:active="list.isLoading.value">
                        {{ message.from_mail }}
                      </skel-skin>
                    </ItemDescription>
                    <ItemTitle>
                      <skel-skin v-bind:active="list.isLoading.value">
                        {{ message.subject }}
                      </skel-skin>
                    </ItemTitle>
                    <ItemDescription>
                      <skel-skin v-bind:active="list.isLoading.value">
                        {{ message.to_mail }}
                      </skel-skin>
                    </ItemDescription>
                  </ItemContent>
                  <ItemActions>
                    <template v-if="list.isLoading.value">
                      <div class="flex size-9 items-center justify-center">
                        <Skeleton class="size-6" />
                      </div>
                    </template>
                    <template v-else>
                      <Button size="icon" variant="ghost" as-child>
                        <router-link
                          v-bind:to="{
                            name: 'embed:email:account:message:detail',
                            params: { accountId, messageId: message.id },
                          }">
                          <i-hugeicons-microscope class="size-6" />
                        </router-link>
                      </Button>
                    </template>
                  </ItemActions>
                </Item>
              </ItemGroup>
            </div>
          </ScrollArea>
          <Pagination
            class="m-2"
            show-edges
            v-slot="{ page }"
            v-bind:items-per-page="list.data.value.per_page"
            v-bind:total="list.data.value.total"
            v-bind:page="list.data.value.page"
            v-on:update:page="handlePageUpdate">
            <PaginationContent v-slot="{ items }">
              <PaginationPrevious />
              <template v-for="(item, index) in items" v-bind:key="index">
                <PaginationItem class="w-12" v-if="item.type === 'page'" v-bind:value="item.value" v-bind:is-active="item.value === page">
                  {{ item.value }}
                </PaginationItem>
                <PaginationEllipsis v-else v-bind:key="item.type" v-bind:index="index" />
              </template>
              <PaginationNext />
            </PaginationContent>
          </Pagination>
        </template>
        <template v-else>
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon" class="size-14">
                <i-hugeicons-mail-at-sign-01 class="size-12" />
              </EmptyMedia>
              <EmptyTitle>
                {{ "The account doesn’t have any messages yet" }}
              </EmptyTitle>
              <EmptyDescription>
                {{ "Messages will appear here once they are syncronized" }}
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        </template>
      </template>
    </CardContent>
  </Card>
</template>
