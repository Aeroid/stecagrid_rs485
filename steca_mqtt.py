#!/usr/bin/env python3
"""
steca_mqtt.py — MQTT bridge for StecaGrid 3600 RS485.

Polls the inverter via RS485, publishes live metrics to MQTT, and subscribes to
a setpoint topic so a home-automation controller can throttle output power.

Power-limit flow
----------------
  Subscribe : <base_topic>/setpoint/power_limit_percent
  Publish   : <base_topic>/<METRIC_NAME>

The setpoint value (float, 0.0–100.0) is applied in the main poll loop via
build_setpoint_percent().  A setpoint frame is only sent when the limit is
strictly less than 100 %, so normal, unthrottled operation adds no write
traffic to the RS485 bus.  The inverter discards the setpoint after ~1 min, so
the loop must re-send it every poll cycle for as long as the limit is active.
"""

import argparse
import threading
import time

import serial           # pip install pyserial
import yaml             # pip install pyyaml
import paho.mqtt.client as mqtt  # pip install paho-mqtt

from StecaGridController import (
    DEBUG,
    SERIAL_BAUDRATE, SERIAL_BYTES, SERIAL_PARITY, SERIAL_SBIT,
    TOPICS,
    build_request,
    getStecaGridResult,
    decode_TotalYield_a,
)
from steca_setpoint import build_setpoint_percent

_DEFAULT_CONFIG = "config.yaml"

# ── Metric definitions ────────────────────────────────────────────────────────
# name → (topic_key in TOPICS dict, result-extractor)
# extractor(val) receives results[5] from getStecaGridResult; returns (float|str, str)
def _float_unit(val):
    if isinstance(val, list) and len(val) >= 2:
        return val[0], val[1]
    return None, None

def _total_yield(val):
    # results[5] is already [float, "Wh"] from decode_TotalYield_a
    return _float_unit(val)

METRICS = {
    "CURRENT_ELECTRICITY_DELIVERY": ("ac_power",      _float_unit),
    "ELECTRICITY_EXPORTED_TOTAL":   ("total_yield",    _total_yield),
    "CURRENT_DAILY_YIELD":          ("daily_yield",    _float_unit),
    "CURRENT_PANEL_POWER":          ("panel_power",    _float_unit),
    "CURRENT_PANEL_VOLTAGE":        ("panel_voltage",  _float_unit),
    "CURRENT_PANEL_CURRENT":        ("panel_current",  _float_unit),
    "SG_SERIAL":                    ("serial",         lambda v: (v[0] if isinstance(v, list) else v, "")),
}


class StecaMqttService:
    def __init__(self, config: dict, verbose: bool = False):
        self._cfg     = config
        self._verbose = verbose

        # Active power-limit setpoint in percent (None = not set / full power)
        self._limit_pct: float | None = None
        self._limit_lock = threading.Lock()

        # Serial port (opened in run())
        self._port: serial.Serial | None = None

        # MQTT client
        self._mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if "mqtt_username" in config:
            self._mqtt.username_pw_set(config["mqtt_username"],
                                        password=config.get("mqtt_password", ""))
        self._mqtt.reconnect_delay_set(min_delay=1, max_delay=30)
        self._mqtt.on_connect    = self._on_connect
        self._mqtt.on_message    = self._on_message
        self._mqtt.on_disconnect = self._on_disconnect

    # ── MQTT callbacks ────────────────────────────────────────────────────────
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            base  = self._cfg["topic"]
            topic = f"{base}/setpoint/power_limit_percent"
            client.subscribe(topic, qos=1)
            if self._verbose:
                print(f"MQTT connected, subscribed to {topic}")
        else:
            print(f"MQTT connect failed: reason={reason_code}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        if self._verbose:
            print(f"MQTT disconnected (reason={reason_code}), will auto-reconnect")

    def _on_message(self, client, userdata, message):
        try:
            payload = message.payload.decode("utf-8").strip()
            pct     = float(payload)
            if not 0.0 <= pct <= 100.0:
                print(f"MQTT setpoint out of range: {pct}")
                return
            with self._limit_lock:
                self._limit_pct = pct
            if self._verbose:
                print(f"MQTT setpoint received: {pct:.1f} %")
        except ValueError:
            print(f"MQTT setpoint invalid payload: {message.payload!r}")

    # ── Serial helpers ────────────────────────────────────────────────────────
    def _open_port(self) -> serial.Serial:
        dev = self._cfg.get("serial_device", "/dev/ttyS0")
        return serial.Serial(
            port=dev, baudrate=SERIAL_BAUDRATE, bytesize=SERIAL_BYTES,
            parity=SERIAL_PARITY, stopbits=SERIAL_SBIT,
            timeout=1, xonxoff=0, rtscts=0,
        )

    def _query(self, topic_key: str):
        """Send a read request, return raw results[5] or None."""
        topic_byte, cmd_byte = TOPICS[topic_key]
        req = build_request(0x01, topic_byte, cmd_byte)
        return getStecaGridResult(self._port, req)

    # ── Setpoint sender ───────────────────────────────────────────────────────
    def _send_setpoint_if_limited(self):
        """Send active-power setpoint when a sub-100 % limit is active."""
        with self._limit_lock:
            pct = self._limit_pct

        if pct is None or pct >= 100.0:
            return

        frame = build_setpoint_percent(pct)
        self._port.reset_input_buffer()
        self._port.write(frame)
        if self._verbose:
            print(f"Setpoint sent: {pct:.1f} %  ({round(pct * 10):d} ‰)")
        # Read (and discard) the ACK so it doesn't pollute the next response
        time.sleep(0.15)
        self._port.reset_input_buffer()

    # ── MQTT connect loop ─────────────────────────────────────────────────────
    def _connect_mqtt(self):
        while True:
            try:
                self._mqtt.connect(self._cfg["mqtt_broker_address"])
                break
            except Exception as e:
                print(f"Can't connect to MQTT broker "
                      f"({self._cfg['mqtt_broker_address']}): {e}")
                time.sleep(5)
        self._mqtt.loop_start()

    # ── Main poll loop ────────────────────────────────────────────────────────
    def run(self):
        self._port = self._open_port()
        if self._verbose:
            print(f"Serial port opened: {self._port.port}")

        self._connect_mqtt()

        base             = self._cfg["topic"]
        poll_interval    = float(self._cfg.get("poll_interval_s", 5))
        values_of_interest = self._cfg.get("values_of_interest", list(METRICS))

        try:
            while True:
                for name in values_of_interest:
                    if name not in METRICS:
                        if self._verbose:
                            print(f"Unknown metric: {name}")
                        continue

                    topic_key, extractor = METRICS[name]
                    val = self._query(topic_key)

                    if self._verbose:
                        print(f"{name}: raw={val!r}")

                    if val is None:
                        continue

                    fval, unit = extractor(val)
                    if fval is None:
                        continue

                    # Skip publishing zero total-yield (inverter offline / night)
                    if name == "ELECTRICITY_EXPORTED_TOTAL" and fval == 0:
                        continue

                    try:
                        payload    = float(fval)
                        mqtt_topic = f"{base}/{name}"
                        pub = self._mqtt.publish(mqtt_topic, payload=payload, qos=0)
                        pub.wait_for_publish()
                        if self._verbose:
                            print(f"MQTT ← {mqtt_topic}: {payload} {unit}")
                    except Exception as e:
                        print(f"MQTT publish failed for {name}: {e}")
                        while not self._mqtt.is_connected():
                            print("MQTT: waiting for reconnect …")
                            time.sleep(5)

                # Apply power-limit setpoint (only if < 100 %)
                self._send_setpoint_if_limited()

                time.sleep(poll_interval)

        except KeyboardInterrupt:
            print()
        finally:
            self._mqtt.loop_stop()
            self._port.close()


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MQTT bridge for StecaGrid 3600 RS485"
    )
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose output")
    parser.add_argument("-c", "--config", default=_DEFAULT_CONFIG,
                        help=f"Config file (default: {_DEFAULT_CONFIG})")
    args = parser.parse_args()

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)

    if not cfg:
        raise SystemExit(f"Empty or invalid config: {args.config}")

    svc = StecaMqttService(cfg, verbose=args.verbose)
    svc.run()
