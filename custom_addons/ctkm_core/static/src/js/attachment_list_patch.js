/** @odoo-module **/

import { AttachmentList } from "@mail/core/common/attachment_list";
import { patch } from "@web/core/utils/patch";

const CTKM_BADGE_FILENAME = /^ctkm_\d+_badge\./i;
const CTKM_BOT_NAME = "OdooBot CTKM";

function isCtkmBotDiscussMessage(message) {
    if (!message) {
        return false;
    }
    const authorName =
        message.authorName ||
        message.author?.name ||
        message.author?.displayName;
    if (authorName === CTKM_BOT_NAME) {
        return true;
    }
    const correspondentName =
        message.thread?.correspondent?.persona?.name ||
        message.thread?.correspondent?.persona?.displayName;
    return correspondentName === CTKM_BOT_NAME;
}

function isCtkmBadgeAttachment(attachment) {
    return CTKM_BADGE_FILENAME.test(attachment?.name || "");
}

patch(AttachmentList.prototype, {
    _shouldHideDelete(attachment) {
        if (isCtkmBotDiscussMessage(this.env.message)) {
            return true;
        }
        return isCtkmBadgeAttachment(attachment);
    },

    get showDelete() {
        if (this.env.inComposer) {
            return true;
        }
        if (isCtkmBotDiscussMessage(this.env.message)) {
            return false;
        }
        const attachment = this.attachment;
        if (attachment && isCtkmBadgeAttachment(attachment)) {
            return false;
        }
        return super.showDelete;
    },

    /**
     * @param {import("models").Attachment} attachment
     */
    showDeleteFor(attachment) {
        if (this._shouldHideDelete(attachment)) {
            return false;
        }
        if (this.env.inComposer) {
            return true;
        }
        if (!attachment.isDeletable) {
            return false;
        }
        return (
            !this.env.message ||
            this.env.message.hasTextContent ||
            (this.env.message && this.props.attachments.length > 1)
        );
    },

    /**
     * @param {import("models").Attachment} attachment
     */
    getActions(attachment) {
        const actions = super.getActions(...arguments);
        if (this._shouldHideDelete(attachment)) {
            return actions.filter((action) => action.icon !== "fa fa-trash");
        }
        return actions;
    },
});
