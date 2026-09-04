# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class CtkmTaskStoreVerifier(models.Model):
    _name = 'ctkm.task.store.verifier'
    _description = 'Xác nhận theo cửa hàng (Phụ trách - Người kiểm soát)'
    _order = 'store_key, id'

    task_id = fields.Many2one(
        'ctkm.task', string='Công việc',
        required=True, ondelete='cascade', index=True,
    )
    store_key = fields.Char(string='Mã cửa hàng')
    store_label = fields.Char(string='Cửa hàng')
    assignee_user_id = fields.Many2one(
        'res.users', string='Phụ trách (Cửa hàng trưởng)',
        domain="[('share', '=', False)]",
    )
    verifier_id = fields.Many2one(
        'hr.employee', string='Người kiểm soát (Quản lý cửa hàng)',
        domain="[('user_id.share', '=', False)]",
    )
    verifier_user_id = fields.Many2one(
        'res.users', related='verifier_id.user_id',
        string='Tài khoản Người kiểm soát',
    )
    no_assignee = fields.Boolean(
        string='Xác nhận trực tiếp (không có Phụ trách)',
        help='Bước không có Phụ trách theo cửa hàng (vd. Bàn giao Tem Tag - '
             'bước 10): Quản lý cửa hàng xác nhận trực tiếp phần cửa hàng của '
             'mình sau khi công việc đã hoàn thành.',
    )
    assignee_completed = fields.Boolean(
        string='Phụ trách đã hoàn thành',
        compute='_compute_assignee_completed',
    )
    verified = fields.Boolean(string='Đã xác nhận', default=False)
    verified_date = fields.Date(string='Ngày xác nhận')
    verified_user_id = fields.Many2one('res.users', string='Người xác nhận')
    received_notified = fields.Boolean(
        string='Đã báo nhận tem/tag',
        help='Đã gửi thông báo cửa hàng đã nhận tem/tag mới tới Quản lý '
             'cửa hàng (tránh gửi lặp khi Cửa hàng trưởng tick nhiều dòng).',
    )

    @api.depends(
        'task_id.state', 'task_id.completion_ids',
        'task_id.completion_ids.done', 'assignee_user_id', 'no_assignee',
        'task_id.store_dispatch_ids', 'task_id.store_dispatch_ids.state',
        'task_id.store_dispatch_ids.store_key', 'store_key', 'store_label',
    )
    def _compute_assignee_completed(self):
        for line in self:
            task = line.task_id
            if task and task._ctkm_is_store_dispatch_step():
                pending = task._ctkm_dispatch_alias_set(('pending',))
                line.assignee_completed = task._ctkm_store_in_allowed(
                    pending, line.store_key, line.store_label,
                )
                continue
            if line.no_assignee:
                # Không có Phụ trách riêng: xem công việc đã bấm Hoàn thành
                # (chờ xác nhận / đã xong) là đủ điều kiện để Quản lý cửa hàng
                # xác nhận phần cửa hàng của mình.
                line.assignee_completed = bool(
                    line.task_id.state in ('waiting_confirm', 'done')
                )
                continue
            if not line.task_id or not line.assignee_user_id:
                line.assignee_completed = False
                continue
            line.assignee_completed = bool(line.task_id.completion_ids.filtered(
                lambda c: c.user_id == line.assignee_user_id and c.done
            ))

    def _ctkm_verify(self, user):
        """Xác nhận phần cửa hàng: chỉ Quản lý cửa hàng ĐÚNG store mới xác nhận được."""
        today = fields.Date.context_today(self)
        is_admin = user.has_group('ctkm_core.group_ctkm_manager')
        for line in self:
            if line.verified or not line.assignee_completed:
                continue
            if not line.verifier_user_id or (
                line.verifier_user_id != user and not is_admin
            ):
                continue
            line.write({
                'verified': True,
                'verified_date': today,
                'verified_user_id': user.id,
            })

    def write(self, vals):
        res = super().write(vals)
        if 'verified' in vals:
            self.env['ctkm.task'].sudo()._ctkm_sync_price_lines_for_programs(
                self.mapped('task_id.program_id')
            )
        return res
