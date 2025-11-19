# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class PaytagItem(models.Model):
    _name = "paytag.item"
    _description = "Item detected by Paytag"

    # Basic identification
    rfid = fields.Char(string="RFID", index=True)
    barcode = fields.Char(string="Barcode", index=True)
    is_ht = fields.Boolean(string="Hard Tag", default=False)

    status = fields.Selection(
        [
            ("added", "Added"),
            ("removed", "Removed"),
            ("paid", "Paid"),
            ("unpaid", "Unpaid"),
            ("neutralized", "Neutralized"),
        ],
        default="added",
        index=True,
    )

    # Link to session
    session_id = fields.Many2one(
        "paytag.session",
        string="Session",
        ondelete="cascade",
    )

    # Timestamps
    first_seen = fields.Datetime(string="First Seen")
    last_seen = fields.Datetime(string="Last Seen")

    # 🔗 Link to real Odoo product variant
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        ondelete="set null",
    )

    # Optional message (we use it in the controller)
    message = fields.Char(string="Message")
