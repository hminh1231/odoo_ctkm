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
    assignee_completed = fields.Boolean(
        string='Phụ trách đã hoàn thành',
        compute='_compute_assignee_completed',
    )
    verified = fields.Boolean(string='Đã xác nhận', default=False)
    verified_date = fields.Date(string='Ngày xác nhận')
    verified_user_id = fields.Many2one('res.users', string='Người xác nhận')

    @api.depends('task_id.completion_ids', 'task_id.completion_ids.done',
                 'assignee_user_id')
    def _compute_assignee_completed(self):
        for line in self:
            if not line.task_id or not line.assignee_user_id:
                line.assignee_completed = False
                continue
            line.assignee_completed = bool(line.task_id.completion_ids.filtered(
                lambda c: c.user_id == line.assignee_user_id and c.done
            ))

    def _ctkm_verify(self, user):
        """Xác nhận phần cửa hàng: chỉ Quản lý cửa hàng ĐÚNG store mới xác nhận được."""
        today = fields.Date.context_today(self)
        for line in self:
            if line.verified or not line.assignee_completed:
                continue
            if not line.verifier_user_id or line.verifier_user_id != user:
                continue
            line.write({
                'verified': True,
                'verified_date': today,
                'verified_user_id': user.id,
            })
