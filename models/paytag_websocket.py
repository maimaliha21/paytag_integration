# -*- coding: utf-8 -*-
import asyncio
import json
import threading
import logging
from datetime import datetime

from odoo import models, fields, api, registry

# aiohttp is required
try:
    from aiohttp import ClientSession, WSMsgType
except Exception:
    ClientSession = None
    WSMsgType = None

_logger = logging.getLogger(__name__)

class PaytagWebsocketService(models.AbstractModel):
    _name = 'paytag.websocket.service'
    _description = 'Paytag Websocket Service'

    # Configuration stored in system parameters would be cleaner; for now simple default
    ws_uri = fields.Char(string="Websocket URI", default="ws://127.0.0.1:8765/ws")

    _thread = None
    _loop = None
    _stop_event = None
    _send_queue = None

    @api.model
    def ensure_running(self):
        """Ensure the websocket background thread is started."""
        if ClientSession is None:
            _logger.error("aiohttp not available. Install aiohttp.")
            return False

        if PaytagWebsocketService._thread and PaytagWebsocketService._thread.is_alive():
            return True

        PaytagWebsocketService._stop_event = threading.Event()
        PaytagWebsocketService._send_queue = asyncio.Queue()

        def run_loop():
            loop = asyncio.new_event_loop()
            PaytagWebsocketService._loop = loop
            try:
                loop.run_until_complete(self._run_forever())
            except Exception as e:
                _logger.exception("Websocket loop exception: %s", e)
            finally:
                loop.close()
        PaytagWebsocketService._thread = threading.Thread(target=run_loop, daemon=True, name="paytag-ws")
        PaytagWebsocketService._thread.start()
        _logger.info("Started Paytag websocket thread")
        return True

    async def _run_forever(self):
        """Main async loop for websocket connection & handling."""
        uri = self.ws_uri or "ws://127.0.0.1:8765/ws"
        retry_delay = 5
        while not PaytagWebsocketService._stop_event.is_set():
            try:
                async with ClientSession() as session:
                    _logger.info("Connecting to Paytag WS: %s", uri)
                    async with session.ws_connect(uri) as ws:
                        _logger.info("Connected to Paytag WS")
                        send_task = asyncio.create_task(self._sender(ws))
                        recv_task = asyncio.create_task(self._receiver(ws))
                        done, pending = await asyncio.wait([send_task, recv_task], return_when=asyncio.FIRST_EXCEPTION)
                        for t in pending:
                            t.cancel()
            except Exception as e:
                _logger.exception("Error in websocket connection: %s", e)
                await asyncio.sleep(retry_delay)

    async def _sender(self, websocket):
        """Sends queued commands to the device. Queue items are dicts."""
        while not PaytagWebsocketService._stop_event.is_set():
            try:
                cmd = await PaytagWebsocketService._send_queue.get()
                if cmd is None:
                    continue
                await websocket.send_json(cmd)
                _logger.info("Sent to Paytag: %s", cmd)
            except Exception as e:
                _logger.exception("Send error: %s", e)
                await asyncio.sleep(1)

    async def _receiver(self, websocket):
        """Receive messages and write to Odoo models."""
        async for message in websocket:
            try:
                if message.type == WSMsgType.TEXT:
                    text = message.data
                    _logger.debug("Received WS message: %s", text)
                    try:
                        payload = json.loads(text)
                    except Exception:
                        _logger.warning("Non-json message: %s", text)
                        continue
                    # Dispatch handling in Odoo environment
                    self._handle_payload(payload)
                elif message.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    _logger.warning("WS closed or error: %s", message)
                    break
            except Exception as e:
                _logger.exception("Receiver loop error: %s", e)

    def _handle_payload(self, payload):
        """
        Called on WS messages (synchronously). Use registry to run inside ORM safely.
        """
        try:
            env = api.Environment(self.env.cr, self.env.uid, self.env.context)
        except Exception:
            # If called from outside normal env, obtain a fresh environment
            with registry(self.env.cr.dbname).cursor() as cr:
                env = api.Environment(cr, 1, {})

        # Use a safe wrapper to avoid long locks on the main thread
        try:
            self._process_message(env, payload)
        except Exception:
            _logger.exception("Failed to process payload: %s", payload)

    def _process_message(self, env, payload):
        """
        Parse payload and create/update session/items.
        This will be executed inside a DB cursor context when invoked from the thread.
        """
        # Minimal routing based on document spec
        # 1) ACTION barcode
        if payload.get('type') == 'barcode':
            action = payload.get('action')
            item = payload.get('item') or {}
            rfid = item.get('rfid') or ''
            barcode = item.get('barcode') or ''
            # Find active session or create one (simple logic: last session not done)
            Session = env['paytag.session'].sudo()
            session = Session.search([('state', 'in', ['waiting', 'scanning'])], limit=1, order='start_time desc')
            if not session:
                session = Session.create({'name': f"session-{datetime.now().strftime('%Y%m%d%H%M%S')}", 'state': 'scanning'})
            # Create or update item
            Item = env['paytag.item'].sudo()
            existing = Item.search([('rfid', '=', rfid), ('session_id', '=', session.id)], limit=1) if rfid else Item.search([('barcode','=',barcode),('session_id','=',session.id)], limit=1)
            vals = {
                'rfid': rfid,
                'barcode': barcode,
                'status': 'added' if action == 'added' else 'removed',
                'session_id': session.id,
                'last_seen': fields.Datetime.now()
            }
            if existing:
                existing.write(vals)
            else:
                vals['first_seen'] = fields.Datetime.now()
                Item.create(vals)
            # Update session state
            if session.state != 'scanning':
                session.sudo().write({'state': 'scanning'})
            _logger.info("Processed barcode action: %s (rfid=%s barcode=%s)", action, rfid, barcode)

        # 2) Neutralizer type action
        elif payload.get('type') == 'neutralizer':
            # payload example: {'type':'neutralizer','action':'tag','status':211,'items':{...},'message':...}
            action = payload.get('action')
            items = payload.get('items') or {}
            barcode = items.get('barcode') if isinstance(items, dict) else None
            Item = env['paytag.item'].sudo()
            if barcode:
                found = Item.search([('barcode', '=', barcode)], limit=1)
                if found:
                    found.sudo().write({'status': 'neutralized'})
            _logger.info("Neutralizer action processed: %s, barcode=%s", action, barcode)

        # 3) Info / status messages
        elif payload.get('type') == 'info' or 'status' in payload:
            _logger.info("Info/status from Paytag: %s", payload)

        else:
            _logger.debug("Unhandled payload: %s", payload)

    @api.model
    def send_command(self, command_dict):
        """
        Queue a command to be sent to the Paytag device.
        Example command_dict: {"command":"start", "request_code":"abc", ...}
        """
        if PaytagWebsocketService._loop and PaytagWebsocketService._send_queue:
            try:
                # Use loop.call_soon_threadsafe to schedule put in queue
                fut = asyncio.run_coroutine_threadsafe(PaytagWebsocketService._send_queue.put(command_dict), PaytagWebsocketService._loop)
                fut.result(timeout=2)
                _logger.debug("Queued command for Paytag: %s", command_dict)
                return True
            except Exception as e:
                _logger.exception("Failed to queue command: %s", e)
                return False
        else:
            _logger.warning("Websocket loop not running; cannot send command.")
            return False

    @api.model
    def stop_service(self):
        if PaytagWebsocketService._stop_event:
            PaytagWebsocketService._stop_event.set()
        _logger.info("Stop signal sent to Paytag service.")
