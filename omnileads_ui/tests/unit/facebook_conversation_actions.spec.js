import FacebookConversationService from '@/services/agent/facebook/conversation_service';
import actions from '@/store/agent/facebook/conversation/actions';
import { resetStoreDataByAction } from '@/utils';

jest.mock('@/services/agent/facebook/conversation_service', () => {
    return jest.fn().mockImplementation(() => ({
        sendAttachmentMessage: jest.fn()
    }));
});

jest.mock('@/utils', () => ({
    resetStoreDataByAction: jest.fn()
}));

const service = FacebookConversationService.mock.results[0].value;

describe('Facebook conversation actions', () => {
    beforeEach(() => {
        jest.clearAllMocks();
    });

    it('publishes a newly sent attachment to the active conversation', async () => {
        const existingMessage = { id: 1, type: 'message' };
        const responseData = {
            id: 2,
            conversation: 10,
            origin: 'page-id',
            sender: { name: 'agent' },
            content: { file: { url: '/media/document.pdf' } },
            status: 'sent',
            timestamp: '2026-08-04T12:00:00Z',
            type: 'file'
        };
        service.sendAttachmentMessage.mockResolvedValue({
            status: 'SUCCESS',
            data: responseData
        });
        const commit = jest.fn();
        const messages = [existingMessage];
        const formData = new FormData();
        formData.append('file', new Blob(['pdf']), 'document.pdf');

        await actions.agtFacebookConversationSendAttachmentMessage(
            { commit, state: { agtFacebookConversationMessages: [] } },
            {
                conversationId: 10,
                formData,
                pageId: 'page-id',
                messages,
                $t: (key) => key
            }
        );

        const updatedMessages = commit.mock.calls[0][1];
        expect(commit).toHaveBeenCalledWith(
            'agtFacebookConversationInitMessages',
            expect.any(Array)
        );
        expect(updatedMessages).toHaveLength(2);
        expect(updatedMessages[1]).toMatchObject({
            id: 2,
            itsMine: true,
            type: 'file',
            message: responseData.content
        });
        expect(messages).toEqual([existingMessage]);
        expect(resetStoreDataByAction).toHaveBeenCalledWith({
            action: 'agtFacebookSetConversationMessages',
            data: updatedMessages
        });
    });
});
