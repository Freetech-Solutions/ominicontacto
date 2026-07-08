<script lang="ts">
import { useQuery } from "@pinia/colada"
import { mande, type MandeError } from "mande"

type Message = {
  id: number
  date: string
  subject: string
  from_mail: string
  from_name: string
  to_mail: string
  to_name: string
  body_html: string
  body_text: string
  message_id: string
  in_reply_to: string
  references: string[]
  attachments: {
    name: string
    url: string
  }[]
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
  Item,
  ItemFooter,
  ItemGroup,
  ItemHeader,
  ScrollArea,
  Table,
  TableBody,
  TableCell,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "~/shadcn"

const { accountId, messageId } = defineProps<{ accountId: number; messageId: number }>()

const api = mande("/email/api/v1/messages")

const retrieve = useQuery<Message, MandeError<any>, undefined>({
  key: ["email-message", messageId],
  query() {
    return api.get<Message>(messageId)
  },
})

function handleRefetch() {
  if (!retrieve.isLoading.value) {
    retrieve.refetch(true)
  }
}
</script>

<template lang="html">
  <Card>
    <div class="grid grid-cols-[auto_1fr] gap-2 px-6">
      <Button variant="secondary" class="rounded-full" size="icon-lg" as-child>
        <router-link
          v-bind:to="{
            name: 'embed:email:account:message:list',
            params: { accountId },
          }">
          <i-hugeicons-arrow-left-01 class="size-8" />
        </router-link>
      </Button>
      <CardHeader class="px-0">
        <CardTitle>
          {{ "Email Message" }}
        </CardTitle>
        <CardDescription>
          {{ "You can view all details about the message" }}
        </CardDescription>
        <CardAction class="flex gap-2">
          <Button size="icon-lg" variant="outline" v-on:click="handleRefetch">
            <i-hugeicons-repost class="size-6" />
          </Button>
        </CardAction>
      </CardHeader>
    </div>
    <CardContent>
      <template v-if="retrieve.status.value === 'error'">
        <Alert variant="destructive">
          <i-hugeicons-alert-circle />
          <AlertTitle>
            {{ "Unable to retrieve message" }}
          </AlertTitle>
          <AlertDescription v-if="retrieve.error.value">
            <p>{{ retrieve.error.value.body?.detail || retrieve.error.value.toString() }}</p>
          </AlertDescription>
        </Alert>
      </template>
      <template v-else>
        <ScrollArea class="-mx-4 max-h-[calc(100vh-150px)] overflow-auto">
          <div class="px-4">
            <ItemGroup class="gap-4" v-if="retrieve.data.value">
              <Item variant="outline">
                <ItemHeader class="overflow-auto">
                  <Table class="text-sm">
                    <TableBody>
                      <TableRow>
                        <TableCell class="text-right">
                          {{ "Date" }}
                        </TableCell>
                        <TableCell>{{ retrieve.data.value.date }}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell class="text-right">
                          {{ "Subject" }}
                        </TableCell>
                        <TableCell>{{ retrieve.data.value.subject }}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell class="text-right">
                          {{ "From" }}
                        </TableCell>
                        <TableCell>
                          {{ retrieve.data.value.from_name }}
                          <{{ retrieve.data.value.from_mail }}>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell class="text-right">
                          {{ "To" }}
                        </TableCell>
                        <TableCell>
                          {{ retrieve.data.value.to_mail }}
                          <{{ retrieve.data.value.to_name }}>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell class="text-right">
                          {{ "Message-ID" }}
                        </TableCell>
                        <TableCell>{{ retrieve.data.value.message_id }}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell class="text-right">
                          {{ "In-Reply-To" }}
                        </TableCell>
                        <TableCell>{{ retrieve.data.value.in_reply_to }}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell class="text-right align-top">
                          {{ "References" }}
                        </TableCell>
                        <TableCell>
                          <ul v-for="reference in retrieve.data.value.references">
                            <li>{{ reference }}</li>
                          </ul>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell class="text-right align-top">
                          {{ "Attachments" }}
                        </TableCell>
                        <TableCell>
                          <ul v-for="attachment in retrieve.data.value.attachments">
                            <li>
                              <Button variant="link" size="sm">
                                <i-hugeicons-attachment-01 />
                                <a v-bind:href="attachment.url" target="_blank">
                                  {{ attachment.name }}
                                </a>
                              </Button>
                            </li>
                          </ul>
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </ItemHeader>
                <ItemFooter class="w-full">
                  <Tabs default-value="text" class="h-[32rem] w-full">
                    <TabsList class="items-center" v-equalize-children-width>
                      <TabsTrigger value="text">{{ "Text" }}</TabsTrigger>
                      <TabsTrigger value="html">{{ "Html" }}</TabsTrigger>
                      <TabsTrigger value="html-preview">{{ "Preview" }}</TabsTrigger>
                    </TabsList>
                    <TabsContent value="text" class="bg-muted overflow-auto rounded border p-1">
                      <pre>{{ retrieve.data.value.body_text }}</pre>
                    </TabsContent>
                    <TabsContent value="html" class="bg-muted overflow-auto rounded border p-1">
                      <p class="font-mono">{{ retrieve.data.value.body_html }}</p>
                    </TabsContent>
                    <TabsContent value="html-preview" class="w-full rounded border">
                      <iframe class="h-full w-full" v-bind:srcdoc="retrieve.data.value.body_html" v-equalize-iframe-height sandbox="" />
                    </TabsContent>
                  </Tabs>
                </ItemFooter>
              </Item>
            </ItemGroup>
          </div>
        </ScrollArea>
      </template>
    </CardContent>
  </Card>
</template>
