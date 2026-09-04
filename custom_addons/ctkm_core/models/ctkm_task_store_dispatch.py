# -*- coding: utf-8 -*-

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError


# Chuỗi bước 10→16: gửi dữ liệu cửa hàng xuống bước kế tiếp.
_CTKM_DISPATCH_CHAIN = (
    (10, 'is_tem_handover_task'),
    (11, 'is_tem_receive_task'),
    (12, 'is_tem_replace_task'),
    (13, 'is_tem_photo_task'),
    (14, 'is_tem_check_task'),
    (15, 'is_tem_price_task'),
    (16, 'is_tem_postcheck_task'),
)
_CTKM_DISPATCH_SEND_RANKS = frozenset(range(10, 16))


class CtkmTaskStoreDispatch(models.Model):
    _name = 'ctkm.task.store.dispatch'
    _description = 'Gửi dữ liệu cửa hàng xuống bước sau'
    _order = 'id'

    task_id = fields.Many2one(
        'ctkm.task', string='Công việc',
        required=True, ondelete='cascade', index=True,
    )
    store_key = fields.Char(string='Mã cửa hàng', required=True, index=True)
    store_label = fields.Char(string='Cửa hàng')
    state = fields.Selection(
        selection=[
            ('pending', 'Chờ xác nhận'),
            ('sent', 'Đã gửi'),
        ],
        string='Trạng thái',
        default='pending',
        required=True,
        index=True,
    )
    sent_date = fields.Datetime(string='Ngày gửi')
    confirmed_user_id = fields.Many2one('res.users', string='Người xác nhận')

    _store_uniq = models.Constraint(
        'UNIQUE(task_id, store_key)',
        'Cửa hàng này đã được gửi dữ liệu rồi.',
    )


class CtkmTask(models.Model):
    _inherit = 'ctkm.task'

    store_dispatch_ids = fields.One2many(
        'ctkm.task.store.dispatch', 'task_id',
        string='Cửa hàng đã gửi dữ liệu', copy=False,
    )
    is_store_dispatch_step = fields.Boolean(
        string='Bước gửi từng cửa hàng',
        compute='_compute_store_dispatch_ui',
    )
    store_dispatch_all_sent = fields.Boolean(
        string='Đã gửi hết cửa hàng',
        compute='_compute_store_dispatch_ui',
    )

    def _ctkm_dispatch_rank(self):
        self.ensure_one()
        for rank, flag in _CTKM_DISPATCH_CHAIN:
            if self[flag]:
                return rank
        return 0

    def _ctkm_is_store_dispatch_step(self):
        return self._ctkm_dispatch_rank() in _CTKM_DISPATCH_SEND_RANKS

    def _ctkm_program_task_by_rank(self, rank):
        self.ensure_one()
        flag = dict(_CTKM_DISPATCH_CHAIN).get(rank)
        if not flag or not self.program_id:
            return self.browse()
        return self.sudo().search([
            ('program_id', '=', self.program_id.id),
            (flag, '=', True),
        ], order='id desc', limit=1)

    @api.depends(
        'is_tem_handover_task', 'is_tem_receive_task', 'is_tem_replace_task',
        'is_tem_photo_task', 'is_tem_check_task', 'is_tem_price_task',
        'store_dispatch_ids', 'store_dispatch_ids.state',
        'store_dispatch_ids.store_key', 'program_id',
    )
    def _compute_store_dispatch_ui(self):
        for task in self:
            task.is_store_dispatch_step = task._ctkm_is_store_dispatch_step()
            if not task.is_store_dispatch_step or not task.program_id:
                task.store_dispatch_all_sent = False
                continue
            stores_map = task.program_id.sudo()._ctkm_step4_store_qty_map()
            if not stores_map:
                # Không có cửa hàng từ file bước 4: dùng nút Hoàn thành như bước thường.
                task.store_dispatch_all_sent = True
                continue
            sent = task._ctkm_dispatch_alias_set(('sent',))
            task.store_dispatch_all_sent = all(
                task._ctkm_store_in_allowed(sent, key, *(stores_map[key].get('keys') or []))
                for key in stores_map
            )

    def _ctkm_dispatch_alias_set(self, states=None):
        self.ensure_one()
        recs = self.sudo().store_dispatch_ids
        if states:
            recs = recs.filtered(lambda rec: rec.state in states)
        aliases = set()
        for rec in recs:
            aliases.update(self._ctkm_store_key_aliases(rec.store_key, rec.store_label))
        return aliases

    @api.model
    def _ctkm_store_in_allowed(self, allowed, *values):
        if allowed is None:
            return True
        if not allowed:
            return False
        return bool(self._ctkm_store_key_aliases(*values) & allowed)

    def _ctkm_upstream_sent_store_keys(self):
        """Tập mã cửa hàng bước trước đã Gửi dữ liệu xuống bước này.

        Gồm cả ``pending`` (đang chờ xác nhận) để bước sau nhận dữ liệu ngay
        khi nhân viên bấm Gửi dữ liệu, không đợi quản lý xác nhận xong.
        ``None`` = không lọc (không thuộc chuỗi 11–16).
        """
        self.ensure_one()
        rank = self._ctkm_dispatch_rank()
        if rank < 11:
            return None
        prev = self._ctkm_program_task_by_rank(rank - 1)
        if not prev:
            return set()
        recs = prev.sudo().store_dispatch_ids
        if not recs:
            return None
        return prev._ctkm_dispatch_alias_set(('pending', 'sent'))

    def _ctkm_dispatch_store_key(self, *values):
        self.ensure_one()
        program = self.program_id.sudo()
        stores_map = program._ctkm_step4_store_qty_map() if program else {}
        if stores_map:
            bucket = program._ctkm_match_store_bucket(stores_map, *values)
            if bucket:
                return bucket
        return self._ctkm_store_canonical_key(*values)

    def _ctkm_completed_store_keys(self):
        """Cửa hàng đã tick xong trên bước này (chưa tính đã gửi)."""
        self.ensure_one()
        program = self.program_id.sudo()
        if not program:
            return []
        stores_map = program._ctkm_step4_store_qty_map()
        rank = self._ctkm_dispatch_rank()
        if not stores_map or rank not in _CTKM_DISPATCH_SEND_RANKS:
            return []
        ratios = program._ctkm_stage_store_ratios(rank, stores_map, self)
        return [
            key for key in sorted(stores_map)
            if (ratios.get(key) or 0.0) >= 0.999
        ]

    def _ctkm_existing_line_store_keys(self):
        """Mã cửa hàng đang có trên bảng của công việc (dùng migrate / khớp)."""
        self.ensure_one()
        keys = set()
        for recs in (
            self.handover_store_ids,
            self.collect_store_ids,
            self.tem_tag_replace_ids,
            self.tem_photo_check_ids,
            self.price_store_ids,
            self.postcheck_store_ids,
            self.print_store_ids,
        ):
            for line in recs:
                store_key = line.store_key if 'store_key' in line._fields else False
                store = line.store if 'store' in line._fields else False
                if store_key:
                    keys.add(store_key)
                canon = self._ctkm_store_canonical_key(store_key, store)
                if canon:
                    keys.add(canon)
        return {key for key in keys if key}

    def _ctkm_store_label_for_key(self, store_key):
        self.ensure_one()
        program = self.program_id.sudo()
        stores_map = program._ctkm_step4_store_qty_map() if program else {}
        aliases = self._ctkm_store_key_aliases(store_key)
        for recs in (
            self.handover_store_ids,
            self.collect_store_ids,
            self.tem_tag_replace_ids,
            self.tem_photo_check_ids,
            self.price_store_ids,
            self.postcheck_store_ids,
        ):
            for line in recs:
                label = line.store if 'store' in line._fields else False
                key = line.store_key if 'store_key' in line._fields else False
                if self._ctkm_store_in_allowed(aliases, key, label):
                    return label or key or store_key
        if store_key in stores_map:
            return store_key
        return store_key

    def _ctkm_user_sendable_store_keys(self):
        """Một cửa hàng đã xong, chưa gửi, thuộc phạm vi người đang bấm."""
        self.ensure_one()
        completed = self._ctkm_completed_store_keys()
        busy = self._ctkm_dispatch_alias_set(('pending', 'sent'))
        available = [
            key for key in completed
            if not self._ctkm_store_in_allowed(busy, key)
        ]
        user = self.env.user
        if user.has_group('ctkm_core.group_ctkm_manager'):
            return available
        my_keys = self._ctkm_user_department_store_keys(user)
        if not my_keys:
            return available
        return [
            key for key in available
            if any(
                self._ctkm_department_matches_store(dept_key, key)
                for dept_key in my_keys
            )
        ]

    def _ctkm_pending_dispatches_for_user(self, user):
        self.ensure_one()
        pending = self.sudo().store_dispatch_ids.filtered(
            lambda rec: rec.state == 'pending'
        ).sorted('id')
        if not pending:
            return pending
        if user.has_group('ctkm_core.group_ctkm_manager'):
            return pending
        if self.store_verifier_ids:
            my_aliases = set()
            for line in self.store_verifier_ids.filtered(
                lambda rec: rec.verifier_user_id == user and not rec.verified
            ):
                my_aliases.update(
                    self._ctkm_store_key_aliases(line.store_key, line.store_label)
                )
            return pending.filtered(
                lambda rec: bool(
                    self._ctkm_store_key_aliases(rec.store_key, rec.store_label)
                    & my_aliases
                )
            )
        if self._user_can_confirm_as_manager(user):
            return pending
        return self.env['ctkm.task.store.dispatch']

    def _ctkm_verifier_lines_for_store(self, store_key, store_label=None):
        self.ensure_one()
        aliases = self._ctkm_store_key_aliases(store_key, store_label)
        return self.store_verifier_ids.filtered(
            lambda line: bool(
                self._ctkm_store_key_aliases(line.store_key, line.store_label)
                & aliases
            )
        )

    def action_send_store_data(self):
        """Gửi đúng 1 cửa hàng đã xong xuống bước sau; quản lý xác nhận từng lần."""
        self.ensure_one()
        user = self.env.user
        if user not in self.user_ids and not user.has_group('ctkm_core.group_ctkm_manager'):
            raise UserError(_('Chỉ người nhận việc mới được bấm Gửi dữ liệu.'))
        if not self._ctkm_is_store_dispatch_step():
            raise UserError(_('Chỉ bước 10–15 mới gửi dữ liệu theo cửa hàng.'))
        if self.state == 'done':
            raise UserError(_('Công việc đã hoàn thành.'))
        if self.store_dispatch_all_sent:
            raise UserError(_(
                'Đã gửi hết cửa hàng. Bấm Hoàn thành rồi Chuyển tiếp.'
            ))
        sendable = self._ctkm_user_sendable_store_keys()
        if not sendable:
            raise UserError(_(
                'Chưa có cửa hàng nào tick xong để gửi. '
                'Hãy hoàn thành công việc của một cửa hàng rồi bấm Gửi dữ liệu.'
            ))
        store_key = sendable[0]
        store_label = self._ctkm_store_label_for_key(store_key)
        Dispatch = self.env['ctkm.task.store.dispatch'].sudo()
        existing = Dispatch.search([
            ('task_id', '=', self.id),
            ('store_key', '=', store_key),
        ], limit=1)
        if existing:
            raise UserError(_(
                'Cửa hàng "%s" đã được gửi dữ liệu rồi.'
            ) % (store_label or store_key))
        dispatch = Dispatch.create({
            'task_id': self.id,
            'store_key': store_key,
            'store_label': store_label or store_key,
            'state': 'pending',
        })
        need_confirm = self._ctkm_task_needs_manager_confirm()
        if self.state == 'todo' and not need_confirm:
            self.with_context(ctkm_internal_state_write=True).write({
                'state': 'progress',
            })

        self.message_post(
            body=_(
                'Đã bấm <b>Gửi dữ liệu</b> cửa hàng <b>%s</b>.'
            ) % escape(store_label or store_key),
            subtype_xmlid='mail.mt_note',
            body_is_html=True,
        )

        if not need_confirm:
            self._ctkm_finalize_store_dispatch(dispatch, user)
            self.invalidate_recordset([
                'store_dispatch_ids', 'store_dispatch_all_sent',
                'is_store_dispatch_step',
            ])
            if self.program_id:
                self.program_id.invalidate_recordset([
                    'stage_progress_json', 'checklist_current_stage_id',
                ])
            return self._ctkm_notify_reload(
                _('Đã gửi dữ liệu'),
                _('Đã gửi cửa hàng "%s" xuống bước sau.') % (
                    store_label or store_key
                ),
            )

        # Có xác nhận quản lý: vẫn đẩy cửa hàng xuống bước sau ngay, để người
        # nhận việc bước sau làm được; xác nhận chỉ chốt lần gửi trên bước này.
        self._ctkm_push_store_to_next_step(store_key, store_label)
        self.with_context(ctkm_internal_state_write=True).write({
            'state': 'waiting_confirm',
            'manager_confirmed': False,
        })
        if self.store_verifier_ids:
            self._notify_store_verifiers(
                store_keys=self._ctkm_store_key_aliases(store_key, store_label)
            )
        else:
            self._notify_org_manager_confirm()
        self.invalidate_recordset([
            'store_dispatch_ids', 'can_confirm_as_manager',
            'store_dispatch_all_sent',
        ])
        if self.program_id:
            self.program_id.invalidate_recordset([
                'stage_progress_json', 'checklist_current_stage_id',
            ])
        confirm_msg = _(
            'Đã gửi dữ liệu cửa hàng "%s". OdooBot CTKM đã gửi yêu cầu '
            'xác nhận tới quản lý.'
        ) % (store_label or store_key)
        if self.sudo().verifier_ids:
            confirm_msg = _(
                'Đã gửi dữ liệu cửa hàng "%s". OdooBot CTKM đã gửi yêu cầu '
                'xác nhận tới Người kiểm soát.'
            ) % (store_label or store_key)
        elif self.store_verifier_ids:
            confirm_msg = _(
                'Đã gửi dữ liệu cửa hàng "%s". OdooBot CTKM đã gửi yêu cầu '
                'xác nhận tới Quản lý cửa hàng.'
            ) % (store_label or store_key)
        return self._ctkm_notify_reload(_('Đã gửi dữ liệu'), confirm_msg)

    def _ctkm_finalize_store_dispatch(self, dispatch, user=None):
        """Đánh dấu đã gửi + đẩy cửa hàng xuống bước sau."""
        self.ensure_one()
        user = user or self.env.user
        dispatch.sudo().write({
            'state': 'sent',
            'sent_date': fields.Datetime.now(),
            'confirmed_user_id': user.id,
        })
        self._ctkm_push_store_to_next_step(
            dispatch.store_key, dispatch.store_label,
        )

    def _ctkm_sync_after_upstream_dispatch(self):
        self.ensure_one()
        this = self.sudo().with_context(ctkm_dispatch_push=True)
        if this.is_tem_receive_task or this.is_tem_replace_task:
            this._ctkm_sync_tem_tag_lines()
        elif this.is_tem_photo_task or this.is_tem_check_task:
            this._ctkm_sync_tem_photo_lines()
        elif this.is_tem_price_task:
            this._ctkm_sync_price_lines()
        elif this.is_tem_postcheck_task:
            this._ctkm_sync_postcheck_lines()

    def _ctkm_push_store_to_next_step(self, store_key, store_label):
        self.ensure_one()
        program = self.program_id.sudo()
        current_line = self.checklist_line_id.sudo()
        if not program or not current_line:
            return
        next_line = program._ctkm_next_checklist_line(current_line)
        if not next_line:
            return
        if not next_line.user_ids:
            self.message_post(
                body=_(
                    'Cửa hàng <b>%s</b> đã gửi nhưng bước sau chưa có người '
                    'phụ trách — dữ liệu sẽ vào khi bước sau được gán người.'
                ) % escape(store_label or store_key),
                subtype_xmlid='mail.mt_note',
                body_is_html=True,
            )
            return
        next_task = next_line._ctkm_ensure_task()
        if next_task:
            next_task.sudo()._ctkm_sync_after_upstream_dispatch()
            if next_line.state == 'todo':
                next_line.with_context(ctkm_task_sync=True).write({
                    'state': 'progress',
                })
            self._ctkm_notify_next_step_store_arrived(
                next_task, store_key, store_label,
            )

    def _ctkm_notify_next_step_store_arrived(self, next_task, store_key, store_label):
        self.ensure_one()
        label = store_label or store_key or ''
        program_name = self.program_name or self.program_id.name or self.name or ''
        step_name = next_task.checklist_step_name or next_task.name or ''
        chiefs = next_task._ctkm_users_for_store_key(store_key)
        recipients = chiefs or next_task.user_ids
        recipients = recipients.filtered(
            lambda user: user and not user.share and user.active and user.partner_id
        )
        body = Markup('<br/>').join([
            Markup('<b>Đã nhận dữ liệu cửa hàng từ bước trước</b>'),
            Markup('Chương trình: <b>%s</b>') % escape(program_name),
            Markup('Cửa hàng: <b>%s</b>') % escape(label),
            Markup('Công việc: <b>%s</b>') % escape(step_name),
            next_task._ctkm_worker_confirmed_button_markup(),
        ])
        for user in recipients:
            try:
                next_task._post_ctkm_bot_dm(user, body)
            except UserError:
                continue
        if recipients:
            self.message_post(
                body=_(
                    'Đã gửi cửa hàng <b>%(store)s</b> xuống bước '
                    '<b>%(step)s</b> (%(users)s).'
                ) % {
                    'store': escape(label),
                    'step': escape(step_name),
                    'users': escape(', '.join(recipients.mapped('name'))),
                },
                subtype_xmlid='mail.mt_note',
                body_is_html=True,
            )

    def action_mark_done(self):
        dispatch = self.filtered(
            lambda task: task._ctkm_is_store_dispatch_step()
            and task.program_id
            and task.program_id.sudo()._ctkm_step4_store_qty_map()
        )
        rest = self - dispatch
        result = True
        if dispatch:
            result = dispatch._ctkm_action_mark_done_after_all_sent()
        if rest:
            result = super().action_mark_done()
        return result

    def _ctkm_action_mark_done_after_all_sent(self):
        """Hoàn thành bước 10–15 chỉ khi đã gửi hết cửa hàng (tiến độ 100%)."""
        user = self.env.user
        done_tasks = self.browse()
        for task in self:
            if user not in task.user_ids and not user.has_group(
                'ctkm_core.group_ctkm_manager'
            ):
                raise UserError(_(
                    'Chỉ người nhận việc mới được bấm Hoàn thành.'
                ))
            if task.state == 'done':
                done_tasks |= task
                continue
            if not task.store_dispatch_all_sent:
                raise UserError(_(
                    'Chưa gửi hết cửa hàng. Hãy bấm Gửi dữ liệu từng cửa hàng '
                    'đến khi tiến độ 100% rồi bấm Hoàn thành.'
                ))
            if task.sudo().store_dispatch_ids.filtered(lambda rec: rec.state == 'pending'):
                raise UserError(_(
                    'Còn cửa hàng đang chờ xác nhận quản lý. '
                    'Hãy chờ xác nhận xong rồi bấm Hoàn thành.'
                ))
            today = fields.Date.context_today(task)
            need_confirm = task._ctkm_task_needs_manager_confirm()
            task.with_context(ctkm_internal_state_write=True).write({
                'state': 'done',
                'manager_confirmed': bool(need_confirm),
                'done_date': task.done_date or today,
            })
            if task.is_tem_handover_task and task.recover_ids:
                task.recover_ids._ctkm_recover_inventory()
            done_tasks |= task
        target = (done_tasks or self)[:1]
        return target._ctkm_notify_reload(
            _('Đã hoàn thành'),
            _('Công việc đã xong. Bấm Chuyển tiếp để giao bước sau.'),
        )

    def action_manager_confirm(self):
        dispatch = self.filtered(lambda task: task._ctkm_is_store_dispatch_step())
        rest = self - dispatch
        result = True
        if dispatch:
            result = dispatch._ctkm_action_confirm_store_dispatch()
        if rest:
            result = super().action_manager_confirm()
        return result

    def _ctkm_action_confirm_store_dispatch(self):
        """Mỗi lần bấm xác nhận = đúng 1 cửa hàng đã Gửi dữ liệu."""
        user = self.env.user
        confirmed = self.browse()
        for task in self:
            if task.state not in ('waiting_confirm', 'done', 'progress'):
                raise UserError(_(
                    'Chỉ xác nhận được sau khi nhân viên đã bấm Gửi dữ liệu.'
                ))
            pending = task._ctkm_pending_dispatches_for_user(user)
            if not pending:
                if task.sudo().store_dispatch_ids.filtered(
                    lambda rec: rec.state == 'pending'
                ):
                    raise UserError(_(
                        'Bạn không phải người xác nhận của cửa hàng đang chờ, '
                        'hoặc cửa hàng đó đã xác nhận.'
                    ))
                raise UserError(_(
                    'Không còn cửa hàng nào đang chờ xác nhận.'
                ))
            dispatch = pending[:1]
            verifier_lines = task._ctkm_verifier_lines_for_store(
                dispatch.store_key, dispatch.store_label,
            ).filtered(lambda line: not line.verified)
            if verifier_lines:
                to_verify = verifier_lines
                if not user.has_group('ctkm_core.group_ctkm_manager'):
                    to_verify = verifier_lines.filtered(
                        lambda line: line.verifier_user_id == user
                    )
                    if not to_verify:
                        raise UserError(_(
                            'Bạn không phải Quản lý cửa hàng của cửa hàng '
                            '"%s".'
                        ) % (dispatch.store_label or dispatch.store_key))
                today = fields.Date.context_today(task)
                to_verify.sudo().write({
                    'verified': True,
                    'verified_date': today,
                    'verified_user_id': user.id,
                })
            task._ctkm_finalize_store_dispatch(dispatch, user)
            still_pending = task.sudo().store_dispatch_ids.filtered(
                lambda rec: rec.state == 'pending'
            )
            if still_pending:
                task.with_context(ctkm_internal_state_write=True).write({
                    'state': 'waiting_confirm',
                    'manager_confirmed': False,
                })
            else:
                task.with_context(ctkm_internal_state_write=True).write({
                    'state': 'progress',
                    'manager_confirmed': False,
                })
            task.invalidate_recordset([
                'store_dispatch_ids', 'store_dispatch_all_sent',
                'can_confirm_as_manager',
            ])
            if task.program_id:
                task.program_id.invalidate_recordset([
                    'stage_progress_json', 'checklist_current_stage_id',
                ])
            store_label = dispatch.store_label or dispatch.store_key
            task.message_post(
                body=_(
                    'Quản lý đã xác nhận cửa hàng <b>%s</b>. '
                    'Dữ liệu đã gửi xuống bước sau.'
                ) % escape(store_label),
                subtype_xmlid='mail.mt_note',
                body_is_html=True,
            )
            confirmed |= task
        target = (confirmed or self)[:1]
        all_sent = target.store_dispatch_all_sent
        if all_sent:
            return target._ctkm_notify_reload(
                _('Đã xác nhận'),
                _(
                    'Đã xác nhận cửa hàng cuối. Tiến độ 100%%. '
                    'Người nhận việc bấm Hoàn thành rồi Chuyển tiếp.'
                ),
            )
        return target._ctkm_notify_reload(
            _('Đã xác nhận'),
            _(
                'Đã xác nhận và gửi cửa hàng xuống bước sau. '
                'Người nhận việc tiếp tục Gửi dữ liệu cửa hàng còn lại.'
            ),
        )

    def write(self, vals):
        if (
            vals.get('manager_confirmed')
            and not self.env.context.get('ctkm_internal_state_write')
            and not self.env.context.get('ctkm_task_sync')
        ):
            if self.filtered(lambda task: task._ctkm_is_store_dispatch_step()):
                raise UserError(_(
                    'Bước 10–15: dùng nút Xác nhận quản lý để xác nhận '
                    'từng cửa hàng đã Gửi dữ liệu, không tick ô này.'
                ))
        return super().write(vals)
