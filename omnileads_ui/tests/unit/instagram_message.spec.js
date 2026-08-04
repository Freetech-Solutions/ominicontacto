import { shallowMount } from '@vue/test-utils';
import InstagramMessage from '@/components/agent/instagram/conversation/Message';

const CardStub = {
    template: '<div><slot name="content" /></div>'
};

describe('Instagram conversation attachments', () => {
    const mountMessage = (message) => shallowMount(InstagramMessage, {
        props: { message },
        global: {
            mocks: {
                $t: (key) => ({
                    'globals.download_file': 'Descargar archivo',
                    'globals.attached_file': 'Archivo adjunto'
                })[key] || key
            },
            stubs: { Card: CardStub, Tag: true }
        }
    });

    it('shows a PDF as a download without embedding it', () => {
        const wrapper = mountMessage({
            id: 1,
            type: 'file',
            message: {
                file: {
                    url: '/media/archivos_instagram/document.pdf',
                    filename: 'document.pdf'
                }
            }
        });

        expect(wrapper.find('iframe').exists()).toBe(false);
        expect(wrapper.get('a.attachment-link').attributes('href'))
            .toBe('/media/archivos_instagram/document.pdf');
        expect(wrapper.get('.attachment-name').text()).toBe('document.pdf');
        expect(wrapper.get('.attachment-icon').classes()).toContain('pi-file-pdf');
    });

    it('supports application attachments without assuming a document payload', () => {
        const wrapper = mountMessage({
            id: 2,
            type: 'application',
            message: {
                application: {
                    url: '/media/archivos_instagram/archive.zip',
                    name: 'archive.zip'
                }
            }
        });

        expect(wrapper.get('a.attachment-link').attributes('href'))
            .toBe('/media/archivos_instagram/archive.zip');
        expect(wrapper.get('.attachment-name').text()).toBe('archive.zip');
    });
});
