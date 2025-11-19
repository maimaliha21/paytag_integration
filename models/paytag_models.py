# -*- coding: utf-8 -*-

from odoo import models, fields


class PaytagSession(models.Model):
    _name = 'paytag.session'
    _description = 'Paytag Customer Session'
    _order = 'id desc'

    name = fields.Char(string="Session Name", default="New Session")
    state = fields.Selection([
        ('idle', 'Idle'),
        ('scanning', 'Scanning'),
        ('payment', 'Payment'),
        ('neutralizing', 'Neutralizing'),
        ('completed', 'Completed'),
        ('error', 'Error'),
    ], default='idle')

    machine_connected = fields.Boolean(default=False)
    last_message = fields.Text()

    item_ids = fields.One2many(
        'paytag.item',
        'session_id',
        string="Items"
    )

    total_items = fields.Integer(compute="_compute_totals")
    paid_items = fields.Integer(compute="_compute_totals")
    unpaid_items = fields.Integer(compute="_compute_totals")

    def _compute_totals(self):
        for rec in self:
            rec.total_items = len(rec.item_ids)
            rec.paid_items = len(rec.item_ids.filtered(lambda i: i.status == 'paid'))
            rec.unpaid_items = len(rec.item_ids.filtered(lambda i: i.status == 'unpaid'))


class PaytagItem(models.Model):
    _name = 'paytag.item'
    _description = 'Item scanned by Paytag'
    _order = 'id desc'

    session_id = fields.Many2one(
        'paytag.session',
        string="Session",
        ondelete='cascade'
    )

    barcode = fields.Char()
    rfid = fields.Char()
    is_ht = fields.Boolean(string="Hard Tag")

    status = fields.Selection([
        ('added', 'Added'),
        ('removed', 'Removed'),
        ('paid', 'Paid'),
        ('unpaid', 'Unpaid'),
    ], default='added')

    message = fields.Char()
    raw_json = fields.Text(string="Raw Event")
