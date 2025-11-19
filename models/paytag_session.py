# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class PaytagSession(models.Model):
    _name = "paytag.session"
    _description = "Paytag Session"

    name = fields.Char(string="Session Name", readonly=True, default="New")
    transaction_number = fields.Char(string="Transaction Number", index=True)
    state = fields.Selection([
        ('waiting', 'Waiting'),
        ('scanning', 'Scanning'),
        ('payment', 'Payment'),
        ('neutralizing', 'Neutralizing'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='waiting', string="State", index=True)
    start_time = fields.Datetime(string="Start Time", default=fields.Datetime.now)
    end_time = fields.Datetime(string="End Time")
    machine_ip = fields.Char(string="Machine IP")
    items_count = fields.Integer(string="Items Count", compute='_compute_items_count')
    paytag_item_ids = fields.One2many('paytag.item', 'session_id', string="Items", copy=False)

    @api.depends('paytag_item_ids')
    def _compute_items_count(self):
        for rec in self:
            rec.items_count = len(rec.paytag_item_ids)
