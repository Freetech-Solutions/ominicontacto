import Index from '@/views/agent/instagram/conversation/Index';
import ImageUploader from '@/views/agent/instagram/conversation/ImageUploader';
import FileUploader from '@/views/agent/instagram/conversation/FileUploader';
import { INSTAGRAM_URL_NAME } from '@/globals/agent/instagram';

export default [
    {
        path: `/${INSTAGRAM_URL_NAME}_conversation/:id`,
        name: `${INSTAGRAM_URL_NAME}_conversation_detail`,
        component: Index
    },
    {
        path: `/${INSTAGRAM_URL_NAME}_image_uploader.html`,
        name: `${INSTAGRAM_URL_NAME}_image_uploader`,
        component: ImageUploader
    },
    {
        path: `/${INSTAGRAM_URL_NAME}_file_uploader.html`,
        name: `${INSTAGRAM_URL_NAME}_file_uploader`,
        component: FileUploader
    }
];
