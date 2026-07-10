/** @odoo-module **/

import { Chatter } from "@mail/chatter/web_portal/chatter";
import { onMounted, onPatched } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => this._ctkmCloseMessageComposer());
        onPatched(() => this._ctkmCloseMessageComposer());
    },

    _ctkmIsProgramChatter() {
        return this.props.threadModel === "ctkm.program";
    },

    _ctkmCloseMessageComposer() {
        if (this._ctkmIsProgramChatter() && this.state.composerType === "message") {
            this.state.composerType = false;
        }
    },

    async onCtkmChatterSendMessage() {
        await this._ctkmSendDiscussNotification();
    },

    async toggleComposer(mode = false, options = {}) {
        if (this._ctkmIsProgramChatter() && mode === "message") {
            await this._ctkmSendDiscussNotification();
            return;
        }
        return super.toggleComposer(mode, options);
    },

    async _ctkmSendDiscussNotification() {
        this.state.composerType = false;
        if (!this.props.threadId) {
            const saved = await this.props.saveRecord?.();
            if (!saved) {
                return;
            }
        }
        const threadId = this.props.threadId || this.props.record?.resId;
        if (!threadId) {
            return;
        }
        try {
            const result = await this.env.services.orm.call(
                "ctkm.program",
                "action_send_discuss_notification",
                [[threadId]]
            );
            if (result?.params?.message) {
                this.env.services.notification.add(result.params.message, {
                    title: result.params.title,
                    type: result.params.type || "success",
                });
            }
            if (typeof this.reloadParentView === "function") {
                await this.reloadParentView();
            }
            if (this.state.thread) {
                await this.load(this.state.thread, ["messages"]);
            }
        } catch {
            // Validation errors are surfaced by the ORM service.
        } finally {
            this.state.composerType = false;
        }
    },
});
