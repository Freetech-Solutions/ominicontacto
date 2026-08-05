import { shallowMount } from '@vue/test-utils';
import FacebookMessage from '@/components/agent/facebook/conversation/Message';

const CardStub = {
    template: '<div><slot name="content" /></div>'
};

describe('Facebook conversation attachments', () => {
    it('does not load a PDF until the user clicks its download link', () => {
        const url = 'https://media.example.com/document.pdf';
        const wrapper = shallowMount(FacebookMessage, {
            props: {
                message: {
                    id: 1,
                    type: 'file',
                    message: { file: { url } }
                }
            },
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

        expect(wrapper.find('iframe').exists()).toBe(false);
        expect(wrapper.get('a.attachment-link').attributes('href')).toBe(url);
        expect(wrapper.get('a.attachment-link').attributes('download')).toBe('');
        expect(wrapper.get('.attachment-name').text()).toBe('document.pdf');
        expect(wrapper.get('.attachment-icon').classes()).toContain('pi-file-pdf');
        expect(wrapper.get('a.attachment-link').text()).toContain('Descargar archivo');
    });

    it('uses the filename provided by Meta when available', () => {
        const url = 'https://media.example.com/opaque-resource';
        const wrapper = shallowMount(FacebookMessage, {
            props: {
                message: {
                    id: 2,
                    type: 'document',
                    message: {
                        document: {
                            url,
                            filename: 'factura.pdf'
                        }
                    }
                }
            },
            global: {
                mocks: { $t: (key) => key },
                stubs: { Card: CardStub, Tag: true }
            }
        });

        expect(wrapper.get('a.attachment-link').attributes('href')).toBe(url);
        expect(wrapper.get('.attachment-name').text()).toBe('factura.pdf');
        expect(wrapper.get('.attachment-icon').classes()).toContain('pi-file-pdf');
    });

    it('uses a localized fallback for opaque attachment URLs', () => {
        const wrapper = shallowMount(FacebookMessage, {
            props: {
                message: {
                    id: 3,
                    type: 'file',
                    message: { file: { url: 'https://media.example.com/opaque-resource' } }
                }
            },
            global: {
                mocks: {
                    $t: (key) => key === 'globals.attached_file' ? 'Archivo adjunto' : key
                },
                stubs: { Card: CardStub, Tag: true }
            }
        });

        expect(wrapper.get('.attachment-name').text()).toBe('Archivo adjunto');
        expect(wrapper.get('.attachment-icon').classes()).toContain('pi-file');
        expect(wrapper.get('.attachment-icon').classes()).not.toContain('pi-file-pdf');
    });
});
