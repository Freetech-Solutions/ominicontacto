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
                mocks: { $t: (key) => key },
                stubs: { Card: CardStub, Tag: true }
            }
        });

        expect(wrapper.find('iframe').exists()).toBe(false);
        expect(wrapper.get('a.attachment-link').attributes('href')).toBe(url);
        expect(wrapper.get('a.attachment-link').attributes('download')).toBe('');
    });

    it('supports document attachment payloads', () => {
        const url = '/media/document.pdf';
        const wrapper = shallowMount(FacebookMessage, {
            props: {
                message: {
                    id: 2,
                    type: 'document',
                    message: { document: { url } }
                }
            },
            global: {
                mocks: { $t: (key) => key },
                stubs: { Card: CardStub, Tag: true }
            }
        });

        expect(wrapper.get('a.attachment-link').attributes('href')).toBe(url);
    });
});
