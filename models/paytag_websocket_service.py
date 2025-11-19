# -*- coding: utf-8 -*-

import threading
import json
import time
import websocket  # install: pip install websocket-client

from odoo import models, api


class PaytagWebsocketService(models.Model):
    _name = 'paytag.websocket.service'
    _description = 'Paytag WebSocket Background Service'

    _ws = None
    _thread = None
    _running = False

    # ------------------------------------------------------
    # PUBLIC API (called from controllers or cron)
    # ------------------------------------------------------

    @api.model
    def ensure_running(self):
        """Called by cron every 1 minute."""
        if not self._running:
            self.start_service()

    @api.model
    def start_service(self):
        """Starts the background WebSocket thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @api.model
    def stop_service(self):
        """Stops the background thread and closes socket."""
        self._running = False
        try:
            if self._ws:
                self._ws.close()
        except:
            pass

    # ------------------------------------------------------
    # INTERNAL: Main loop
    # ------------------------------------------------------

    def _run(self):
        """Main WebSocket connection loop."""
        ws_url = "ws://127.0.0.1:8765/ws"   # <-- change to your machine IP

        while self._running:
            try:
                self._ws = websocket.WebSocketApp(
                    ws_url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )

                self._ws.on_open = self._on_open

                # Blocking call — stays until disconnect
                self._ws.run_forever()

            except Exception as e:
                self.env.cr.rollback()
                self.env['ir.logging'].create({
                    'name': 'PaytagWebSocket',
                    'type': 'server',
                    'level': 'ERROR',
                    'message': f"WebSocket crashed: {str(e)}",
                    'path': __name__,
                    'line': '0',
                    'func': '_run',
                })

            # Wait then reconnect
            time.sleep(3)

    # ------------------------------------------------------
    # WEBSOCKET CALLBACKS
    # ------------------------------------------------------

    def _on_open(self, ws):
        self._log("WebSocket connected")

    def _on_message(self, ws, message):
        """Handle incoming messages."""
        self._log(f"Received: {message}")

        try:
            data = json.loads(message)
        except:
            return

        # TODO: Next steps → save events into Odoo
        # We will write this after setting up the models.

    def _on_error(self, ws, error):
        self._log(f"Error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        self._log("WebSocket closed")

    # ------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------

    def _log(self, message):
        """Small logging helper."""
        self.env['ir.logging'].create({
            'name': 'PaytagWebSocket',
            'type': 'server',
            'level': 'INFO',
            'message': message,
            'path': __name__,
            'line': '0',
        })

    # ------------------------------------------------------
    # SEND COMMANDS TO PAYTAG
    # ------------------------------------------------------

    @api.model
    def send_command(self, payload):
        """Send JSON command to Paytag machine."""
        if self._ws:
            try:
                self._ws.send(json.dumps(payload))
            except:
                self._log("Failed to send command: connection lost")
