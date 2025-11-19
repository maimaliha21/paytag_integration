# -*- coding: utf-8 -*-
{
    "name": "Paytag Integration",
    "version": "1.0.0",
    "summary": "Integrate Paytag RFID/Neutralizer devices with Odoo via WebSocket",
    "description": "WebSocket client and REST endpoints to control Paytag machines, manage sessions and items, and expose endpoints for Flutter apps.",
    "author": "You",
    "website": "",
    "category": "Point of Sale",
    "depends": ["base", "product"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml"
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
