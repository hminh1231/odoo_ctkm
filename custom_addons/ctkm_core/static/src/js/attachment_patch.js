/** @odoo-module **/

import { Attachment } from "@mail/core/common/attachment_model";
import { patch } from "@web/core/utils/patch";

const CTKM_BADGE_FILENAME = /^ctkm_\d+_badge\./i;
const CTKM_BOT_NAME = "OdooBot CTKM";

/** @type {import("models").Attachment} */
const attachmentPatch = {
    get isDeletable() {
        const authorName =
            this.message?.authorName ||
            this.message?.author?.name ||
            this.message?.author?.displayName;
        if (
            authorName === CTKM_BOT_NAME ||
            CTKM_BADGE_FILENAME.test(this.name || "")
        ) {
            return false;
        }
        return super.isDeletable;
    },
};

patch(Attachment.prototype, attachmentPatch);
