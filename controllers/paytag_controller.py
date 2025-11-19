# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request, Response
import json
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class PaytagAPI(http.Controller):

    # ------------- Helpers -------------

    def _cors_headers(self):
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }

    def _json(self, data, status=200):
        return Response(
            json.dumps(data, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
            status=status,
            headers=self._cors_headers(),
        )

    # ------------- Health check -------------

    @http.route(
        "/api/paytag/health",
        type="http",
        auth="none",
        methods=["GET", "OPTIONS"],
        csrf=False,
    )
    def health(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return Response(status=200, headers=self._cors_headers())

        return self._json(
            {
                "status": "ok",
                "message": "Paytag integration is installed",
                "time": datetime.utcnow().isoformat() + "Z",
            }
        )

    # ------------- Start session -------------

    @http.route(
        "/api/paytag/start",
        type="http",
        auth="none",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def start_session(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return Response(status=200, headers=self._cors_headers())

        try:
            body = request.httprequest.data or b"{}"
            data = json.loads(body.decode("utf-8"))
        except Exception:
            data = {}

        transaction_number = (
            data.get("transaction_number")
            or f"tx-{int(datetime.now().timestamp())}"
        )
        request_code = data.get("request_code") or transaction_number
        version = data.get("version") or "odoo-paytag-1.0"

        # Ensure WebSocket service is running
        ws_service = request.env["paytag.websocket.service"].sudo()
        ws_service.ensure_running()

        # Create a new session record
        session = request.env["paytag.session"].sudo().create(
            {
                "name": f"Session {transaction_number}",
                "transaction_number": transaction_number,
                "state": "scanning",
            }
        )

        # Build Paytag command
        cmd = {
            "command": "start",
            "request_code": request_code,
            "transaction_number": transaction_number,
            "version": version,
            "message": "Start from Odoo",
        }

        ws_service.send_command(cmd)

        return self._json(
            {
                "success": True,
                "session_id": session.id,
                "transaction_number": transaction_number,
            }
        )

    # ------------- Get items for a session -------------

    @http.route(
        "/api/paytag/items",
        type="http",
        auth="none",
        methods=["GET", "OPTIONS"],
        csrf=False,
    )
    def get_items(self, session_id=None, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return Response(status=200, headers=self._cors_headers())

        Session = request.env["paytag.session"].sudo()

        # session_id can come from query string or from internal call
        if session_id:
            try:
                session = Session.browse(int(session_id))
            except Exception:
                session = Session.browse()  # empty recordset
        else:
            session = Session.search([], limit=1, order="id desc")

        if not session:
            return self._json(
                {"success": False, "error": "No session found"},
                status=404,
            )

        items_data = []
        for item in session.paytag_item_ids:
            product = item.product_id
            items_data.append(
                {
                    "id": item.id,
                    "barcode": item.barcode or "",
                    "rfid": item.rfid or "",
                    "is_ht": bool(item.is_ht),
                    "status": item.status or "",
                    "message": item.message or "",
                    "product": {
                        "id": product.id,
                        "name": product.display_name,
                        "default_code": product.default_code,
                        "price": product.lst_price,
                        "qty_available": product.qty_available,
                    }
                    if product
                    else None,
                }
            )

        # compute counts from items
        total_items = len(session.paytag_item_ids)
        paid_items = len(
            session.paytag_item_ids.filtered(lambda i: i.status == "paid")
        )
        unpaid_items = len(
            session.paytag_item_ids.filtered(
                lambda i: i.status in ("unpaid", "added", "removed")
            )
        )

        return self._json(
            {
                "success": True,
                "session_id": session.id,
                "state": session.state,
                "machine_connected": False,  # placeholder for now
                "items": items_data,
                "total_items": total_items,
                "paid_items": paid_items,
                "unpaid_items": unpaid_items,
            }
        )

    # ------------- Ask machine to refresh items (get_items command) -------------

    @http.route(
        "/api/paytag/get_items",
        type="http",
        auth="none",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def command_get_items(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return Response(status=200, headers=self._cors_headers())

        try:
            body = request.httprequest.data or b"{}"
            data = json.loads(body.decode("utf-8"))
        except Exception:
            data = {}

        request_code = data.get("request_code") or f"req-{int(datetime.now().timestamp())}"

        ws_service = request.env["paytag.websocket.service"].sudo()
        ws_service.ensure_running()

        cmd = {
            "command": "get_items",
            "request_code": request_code,
            "message": "Get items from Odoo",
        }

        ws_service.send_command(cmd)

        # We can't wait for the response over HTTP, so just return current DB state
        return self.get_items(session_id=data.get("session_id"))

    # ------------- Neutralize -------------

    @http.route(
        "/api/paytag/neutralize",
        type="http",
        auth="none",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def neutralize(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return Response(status=200, headers=self._cors_headers())

        try:
            body = request.httprequest.data or b"{}"
            data = json.loads(body.decode("utf-8"))
        except Exception:
            data = {}

        barcodes = data.get("barcodes", [])
        transaction_number = data.get("transaction_number") or ""
        request_code = data.get("request_code") or f"req-{int(datetime.now().timestamp())}"

        ws_service = request.env["paytag.websocket.service"].sudo()
        ws_service.ensure_running()

        cmd = {
            "command": "neutralize",
            "request_code": request_code,
            "transaction_number": transaction_number,
            "barcodes": barcodes,
            "options": data.get("options", []),
            "message": "Neutralize from Odoo",
        }

        ws_service.send_command(cmd)

        return self._json(
            {
                "success": True,
                "queued_barcodes": len(barcodes),
            }
        )

    # ------------- Stop -------------

    @http.route(
        "/api/paytag/stop",
        type="http",
        auth="none",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def stop(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return Response(status=200, headers=self._cors_headers())

        try:
            body = request.httprequest.data or b"{}"
            data = json.loads(body.decode("utf-8"))
        except Exception:
            data = {}

        request_code = data.get("request_code") or f"req-{int(datetime.now().timestamp())}"

        ws_service = request.env["paytag.websocket.service"].sudo()
        ws_service.ensure_running()

        cmd = {
            "command": "stop",
            "request_code": request_code,
            "message": "Stop from Odoo",
        }

        ws_service.send_command(cmd)

        # Optionally close last session
        Session = request.env["paytag.session"].sudo()
        if data.get("session_id"):
            try:
                session = Session.browse(int(data.get("session_id")))
            except Exception:
                session = Session.browse()
        else:
            session = Session.search([], limit=1, order="id desc")

        if session:
            session.state = "done"

        return self._json({"success": True})

    # ------------- Test endpoint: add item to a session (no real machine) -------------

    @http.route(
        "/api/paytag/add_item",
        type="http",
        auth="none",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def add_item(self, **kwargs):
        """
        Test-only helper to simulate a scanned item.

        Body JSON example:
        {
          "session_id": 3,
          "barcode": "TEST001",
          "rfid": "RFID123",
          "is_ht": true
        }
        """
        if request.httprequest.method == "OPTIONS":
            return Response(status=200, headers=self._cors_headers())

        try:
            body = request.httprequest.data or b"{}"
            data = json.loads(body.decode("utf-8"))
        except Exception:
            data = {}

        # Required
        session_id = int(data.get("session_id") or 0)

        # Optional
        barcode = (data.get("barcode") or "").strip()
        rfid = (data.get("rfid") or "").strip()
        is_ht = bool(data.get("is_ht", False))

        if not session_id:
            return self._json(
                {"success": False, "error": "session_id is required"},
                status=400,
            )

        Session = request.env["paytag.session"].sudo()
        session = Session.browse(session_id)
        if not session:
            return self._json(
                {"success": False, "error": "Session not found"},
                status=404,
            )

        Product = request.env["product.product"].sudo()
        product = None
        if barcode:
            product = Product.search(
                [
                    "|",
                    ("barcode", "=", barcode),
                    ("default_code", "=", barcode),
                ],
                limit=1,
            )

        item_vals = {
            "session_id": session.id,
            "barcode": barcode,
            "rfid": rfid,
            "is_ht": is_ht,
            "status": "added",
            "first_seen": fields.Datetime.now(),
            "last_seen": fields.Datetime.now(),
            "product_id": product.id if product else False,
            "message": "Test item from API",
        }

        item = request.env["paytag.item"].sudo().create(item_vals)

        return self._json(
            {
                "success": True,
                "item_id": item.id,
                "matched_product": bool(product),
            }
        )
