#!/usr/bin/env python3
"""
steca_mqtt.py — MQTT bridge for StecaGrid 3600 RS485.

Polls the inverter via RS485, publishes live metrics to MQTT, and subscribes to
a setpoint topic so a home-automation controller can throttle output power.

Power-limit flow
----------------
  Subscribe : <base_topic>/setpoint/power_limit_percent   (float 0.0–100.0)
  State     : <base_topic>/setpoint/power_limit_percent/state
  Metrics   : <base_topic>/<METRIC_NAME>

Setpoint behaviour
------------------
- < 100 %: frame is re-sent every poll cycle because the inverter resets its
  setpoint after ~1 min.  Sending continues until a new value arrives.
- = 100 %: frame is sent once and repeated only until the inverter ACKs it
  (status Ok).  After that no further write traffic is produced.

Home Assistant MQTT autodiscovery
----------------------------------
Enable with  ha_discovery: true  in config.yaml.  Sensor and number (setpoint)
entities are announced under  <ha_discovery_prefix>/sensor/  and
<ha_discovery_prefix>/number/  with retain=True on every MQTT connect.
"""

import argparse
import json
import re
import threading
import time

import serial           # pip install pyserial
import yaml             # pip install pyyaml
import paho.mqtt.client as mqtt  # pip install paho-mqtt

from StecaGridController import (
    SERIAL_BAUDRATE, SERIAL_BYTES, SERIAL_PARITY, SERIAL_SBIT,
    TOPICS,
    build_request,
    getStecaGridResult,
    read_complete_frame,
    process_steca485,
)
from steca_setpoint import build_setpoint_percent

_DEFAULT_CONFIG = "config.yaml"

# ── Metric definitions ────────────────────────────────────────────────────────
# name → (topic_key in TOPICS dict, result-extractor)
# extractor(val) receives results[5] from getStecaGridResult; returns (value, unit_str)
# value may be float or str; unit_str is for logging only.
def _float_unit(val):
    if isinstance(val, list) and len(val) >= 2:
        return val[0], val[1]
    return None, None

METRICS = {
    "CURRENT_ELECTRICITY_DELIVERY": ("ac_power",      _float_unit),
    "ELECTRICITY_EXPORTED_TOTAL":   ("total_yield",    _float_unit),
    "CURRENT_DAILY_YIELD":          ("daily_yield",    _float_unit),
    "CURRENT_PANEL_POWER":          ("panel_power",    _float_unit),
    "CURRENT_PANEL_VOLTAGE":        ("panel_voltage",  _float_unit),
    "CURRENT_PANEL_CURRENT":        ("panel_current",  _float_unit),
    "SG_SERIAL":                    ("serial",         lambda v: (v[0] if isinstance(v, list) else v, "")),
}

# ── Home Assistant autodiscovery metadata ─────────────────────────────────────
# name → (friendly_name, device_class, unit_of_measurement, state_class)
# device_class / unit / state_class may be None for string-value entities.
_HA_SENSOR_META = {
    "CURRENT_ELECTRICITY_DELIVERY": ("AC Power",      "power",   "W",  "measurement"),
    "ELECTRICITY_EXPORTED_TOTAL":   ("Total Yield",   "energy",  "Wh", "total_increasing"),
    "CURRENT_DAILY_YIELD":          ("Daily Yield",   "energy",  "Wh", "total_increasing"),
    "CURRENT_PANEL_POWER":          ("Panel Power",   "power",   "W",  "measurement"),
    "CURRENT_PANEL_VOLTAGE":        ("Panel Voltage", "voltage", "V",  "measurement"),
    "CURRENT_PANEL_CURRENT":        ("Panel Current", "current", "A",  "measurement"),
    "SG_SERIAL":                    ("Serial Number", None,      None, None),
}


def _node_id(base_topic: str) -> str:
    """Derive a safe HA node_id from the MQTT base topic."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", base_topic)


class StecaMqttService:
    def __init__(self, config: dict, verbose: bool = False):
        self._cfg     = config
        self._verbose = verbose

        # Setpoint state (protected by _limit_lock)
        self._limit_pct: float | None = None   # desired setpoint; None = not set
        self._limit_confirmed = False           # True once inverter ACKed current value
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
        if reason_code != 0:
            print(f"MQTT connect failed: reason={reason_code}")
            return

        base  = self._cfg["topic"]
        topic = f"{base}/setpoint/power_limit_percent"
        client.subscribe(topic, qos=1)
        if self._verbose:
            print(f"MQTT connected, subscribed to {topic}")

        if self._cfg.get("ha_discovery", False):
            self._publish_ha_discovery()

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
                self._limit_pct       = pct
                self._limit_confirmed = False   # new value must be (re-)sent
            # Echo current setpoint to state topic so HA reflects it immediately
            state_topic = f"{self._cfg['topic']}/setpoint/power_limit_percent/state"
            self._mqtt.publish(state_topic, payload=pct, qos=0, retain=True)
            if self._verbose:
                print(f"MQTT setpoint received: {pct:.1f} %")
        except ValueError:
            print(f"MQTT setpoint invalid payload: {message.payload!r}")

    # ── Home Assistant autodiscovery ──────────────────────────────────────────
    def _publish_ha_discovery(self):
        base    = self._cfg["topic"]
        prefix  = self._cfg.get("ha_discovery_prefix", "homeassistant")
        devname = self._cfg.get("ha_device_name", "StecaGrid 3600")
        node    = _node_id(base)

        device = {
            "identifiers": [node],
            "name":         devname,
            "model":        "StecaGrid 3600",
            "manufacturer": "Steca",
        }

        for metric, (fname, dclass, unit, sclass) in _HA_SENSOR_META.items():
            cfg: dict = {
                "name":        fname,
                "state_topic": f"{base}/{metric}",
                "unique_id":   f"{node}_{metric}",
                "device":      device,
            }
            if dclass:
                cfg["device_class"] = dclass
            if unit:
                cfg["unit_of_measurement"] = unit
            if sclass:
                cfg["state_class"] = sclass

            disc_topic = f"{prefix}/sensor/{node}/{metric}/config"
            self._mqtt.publish(disc_topic,
                               payload=json.dumps(cfg), qos=1, retain=True)
            if self._verbose:
                print(f"HA discovery → {disc_topic}")

        # Number entity for power-limit setpoint
        setpoint_cmd   = f"{base}/setpoint/power_limit_percent"
        setpoint_state = f"{setpoint_cmd}/state"
        num_cfg = {
            "name":                "Power Limit",
            "command_topic":       setpoint_cmd,
            "state_topic":         setpoint_state,
            "min":                 0,
            "max":                 100,
            "step":                1,
            "unit_of_measurement": "%",
            "icon":                "mdi:solar-power",
            "unique_id":           f"{node}_power_limit_percent",
            "device":              device,
            "optimistic":          False,
        }
        disc_topic = f"{prefix}/number/{node}/power_limit_percent/config"
        self._mqtt.publish(disc_topic,
                           payload=json.dumps(num_cfg), qos=1, retain=True)
        if self._verbose:
            print(f"HA discovery → {disc_topic}")

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

    # ── Setpoint logic ────────────────────────────────────────────────────────
    def _send_setpoint(self, pct: float) -> bool:
        """Write a setpoint frame and return True when the inverter ACKs Ok."""
        frame = build_setpoint_percent(pct)
        self._port.reset_input_buffer()
        self._port.write(frame)
        ack = read_complete_frame(self._port, timeout_s=0.5)
        if ack is None:
            if self._verbose:
                print(f"Setpoint {pct:.1f} %: no ACK")
            return False
        result = process_steca485(ack)
        if result and len(result) >= 6 and isinstance(result[5], tuple):
            status, name = result[5]
            ok = (status == 0)
            if self._verbose:
                print(f"Setpoint {pct:.1f} % ({round(pct*10):d} ‰): ACK {name}"
                      f" {'✓' if ok else '✗'}")
            return ok
        if self._verbose:
            print(f"Setpoint {pct:.1f} %: ACK parse failed")
        return False

    def _handle_setpoint(self):
        """Send the current setpoint to the inverter when needed.

        < 100 %: re-send every cycle — the inverter resets its setpoint after
                 ~1 min so continuous repetition is required.
        = 100 %: send once and stop after the inverter confirms it.
        """
        with self._limit_lock:
            pct       = self._limit_pct
            confirmed = self._limit_confirmed

        if pct is None:
            return
        if pct >= 100.0 and confirmed:
            return  # already sent and ACKed, no need to repeat

        ok = self._send_setpoint(pct)
        if ok and pct >= 100.0:
            with self._limit_lock:
                self._limit_confirmed = True

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

        base               = self._cfg["topic"]
        poll_interval      = float(self._cfg.get("poll_interval_s", 5))
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
                        # String metrics (e.g. serial number) publish as-is
                        payload    = fval if isinstance(fval, str) else float(fval)
                        mqtt_topic = f"{base}/{name}"
                        pub = self._mqtt.publish(mqtt_topic, payload=payload, qos=0)
                        pub.wait_for_publish()
                        if self._verbose:
                            print(f"MQTT ← {mqtt_topic}: {payload} {unit}".rstrip())
                    except Exception as e:
                        print(f"MQTT publish failed for {name}: {e}")
                        while not self._mqtt.is_connected():
                            print("MQTT: waiting for reconnect …")
                            time.sleep(5)

                self._handle_setpoint()

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
