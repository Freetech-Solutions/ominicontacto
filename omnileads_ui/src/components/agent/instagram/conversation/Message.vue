<template>
  <Card class="border-round-xl" :class="getClasses(message?.itsMine)" style="max-width:65%">
    <template #content>
      <div class="py-0 my-0">
        {{ message?.content }}
        <div v-if="message.type==='message' || message.type==='quick_reply'">
          <p class="mt-2 mb-3 message-text">
            {{ message?.message.text }}
          </p>
        </div>
        <div v-if="message.type==='template'">
          <p class="mt-2 mb-3 message-text">
            {{ message?.message }}
          </p>
        </div>

        <div v-if="message.type==='image'">
          <a :href="getSafeMediaUrl(message.message.image.url)" style="text-decoration: none; color: inherit;" target="_blank" rel="noopener noreferrer" download>
            <Image :src="getSafeMediaUrl(message.message.image.url)" width="250" />
          </a>
        </div>
        <div v-if="isDownloadableAttachment(message)">
          <div class="attachment-card">
            <i :class="getAttachmentIcon(message)" class="attachment-icon"></i>
            <div class="attachment-details">
              <span class="attachment-name" :title="getAttachmentName(message)">
                {{ getAttachmentName(message) }}
              </span>
              <a
                :href="getAttachmentUrl(message)"
                class="attachment-link"
                target="_blank"
                rel="noopener noreferrer"
                download
              >
                <i class="pi pi-download mr-2"></i>
                <span>{{ $t('globals.download_file') }}</span>
              </a>
            </div>
          </div>
        </div>
        <div v-if="message.type==='audio'">
          <audio controls>
            <source :src="getSafeMediaUrl(message.message.audio.url)" type="audio/ogg">
          </audio>
        </div>
        <div v-if="message.type==='video'">
          <video width="320" height="240" controls>
            <source :src="getSafeMediaUrl(message.message.video.url)" type="video/mp4">
          </video>
        </div>
        <div v-if="message.type==='list'">
          <p class="mt-2 mb-3 message-text">
            {{ message?.message.text }}
          </p>
          <button class="btn btn-primary"
            v-for="button in message?.message?.buttons"
            :key="button.payload"
          >
            {{ button.title }}
          </button>
        </div>
        <div v-if="message?.fail_reason" class="flex justify-content-end flex-wrap">
          <Tag severity="danger" :value="message?.fail_reason"></Tag>
        </div>
        <div class="flex justify-content-end flex-wrap">
          <div class="flex align-items-center justify-content-center">
            <small class="font-italic">
              {{ message?.date?.toLocaleString() }}
            </small>
            <i v-if="message?.itsMine" class="ml-2" :class="getIconMessageStatus(message?.status)" :style="{color: getIconStatusColor(message?.status)}" ></i>
          </div>
        </div>
      </div>
    </template>
  </Card>
</template>

<script>
import { INSTAGRAM_MESSAGE } from '@/globals/agent/instagram';
import { getSafeMediaUrl } from '@/utils';
import Image from 'primevue/image';
export default {
    props: {
        message: {
            type: Object,
            default: () => {}
        }
    },
    components: {
        Image
    },
    methods: {
        getSafeMediaUrl,
        isDownloadableAttachment (message) {
            return ['file', 'document', 'application'].includes(message?.type);
        },
        getAttachment (message) {
            const content = message?.message || {};
            return content.file || content.document || content.application || {};
        },
        getAttachmentUrl (message) {
            return getSafeMediaUrl(this.getAttachment(message).url || message?.file);
        },
        getAttachmentName (message) {
            const attachment = this.getAttachment(message);
            const providedName = attachment.name || attachment.filename || attachment.file_name;
            if (providedName) {
                return providedName;
            }

            const sourceUrl = attachment.url || message?.file;
            if (typeof sourceUrl === 'string') {
                try {
                    const pathname = new URL(sourceUrl, window.location.origin).pathname;
                    const filename = decodeURIComponent(pathname.split('/').pop() || '');
                    if (filename && /\.[a-z0-9]{1,10}$/i.test(filename)) {
                        return filename;
                    }
                } catch {
                    // Meta may provide an opaque URL; use the localized fallback below.
                }
            }
            return this.$t('globals.attached_file');
        },
        getAttachmentIcon (message) {
            const attachment = this.getAttachment(message);
            const mimeType = attachment.mime_type || attachment.content_type || '';
            const filename = this.getAttachmentName(message);
            const isPdf = mimeType.toLowerCase().includes('pdf') || /\.pdf$/i.test(filename);
            return isPdf ? 'pi pi-file-pdf attachment-icon-pdf' : 'pi pi-file';
        },
        getClasses (itsMine) {
            if (itsMine) {
                return {
                    'bg-green-200': true,
                    'message-r': true
                };
            } else {
                return {
                    'bg-gray-200': true,
                    'message-l': true
                };
            }
        },
        getIconStatusColor (status) {
            if (status === INSTAGRAM_MESSAGE.STATUS.READ) {
                return 'slateblue';
            } else if (status === INSTAGRAM_MESSAGE.STATUS.ERROR) {
                return 'red';
            }
        },
        getIconMessageStatus (status) {
            if (status === INSTAGRAM_MESSAGE.STATUS.SENT) {
                return 'pi pi-check';
            } else if (status === INSTAGRAM_MESSAGE.STATUS.DELIVERED) {
                return 'pi pi-check-circle';
            } else if (status === INSTAGRAM_MESSAGE.STATUS.READ) {
                return 'pi pi-check-circle';
            } else if (status === INSTAGRAM_MESSAGE.STATUS.ERROR) {
                return 'pi pi-times-circle';
            }
        }
    }
};
</script>

<style scoped>
.message-r {
  float: right;
}
.message-l {
  float: left;
}
.message-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.attachment-card {
  align-items: center;
  background-color: rgba(255, 255, 255, 0.65);
  border-radius: 0.5rem;
  display: flex;
  gap: 0.75rem;
  max-width: 18rem;
  padding: 0.75rem;
}
.attachment-icon {
  color: #607d8b;
  flex-shrink: 0;
  font-size: 2rem;
}
.attachment-icon-pdf {
  color: #d32f2f;
}
.attachment-details {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.attachment-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attachment-link {
  align-items: center;
  color: #1565c0;
  display: flex;
  margin-top: 0.35rem;
  text-decoration: none;
}
.attachment-link:hover {
  text-decoration: underline;
}
</style>
