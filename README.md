# StecaGrid 3600 RS485 Tools

Tools to read out, control, and integrate StecaGrid 3600 solar inverters via RS485.
Developed and tested against firmware from 2013 (see [firmware versions](#based-on-versions)).

**Highlights**
- MQTT bridge with [Home Assistant autodiscovery](#home-assistant-autodiscovery) and [power-limit setpoint control](#power-limit-setpoint)
- Multi-inverter support — one service, multiple RS485 addresses
- Full protocol implementation with verified CRC1 + CRC2
- Historical yield read-out (10-min curves, daily, monthly, yearly)
- Passive RS485 sniffer for bus analysis

---

## steca_mqtt.py — MQTT Bridge Service

Polls one or more inverters on the RS485 bus, publishes live metrics to an MQTT broker,
and accepts per-inverter power-limit setpoints via MQTT subscription.

### Install

```bash
pip3 install pyserial pyyaml paho-mqtt
```

### Configuration — `config.yaml`

```yaml
# MQTT broker
mqtt_broker_address: 'nas.ds18'
mqtt_username: 'mqtt_user'
mqtt_password: 'xyzxyz'

# RS485 serial port (shared by all inverters on the bus)
serial_device: /dev/ttyS0

# Poll interval in seconds
poll_interval_s: 5

# Home Assistant MQTT autodiscovery (see section below)
ha_discovery: false
ha_discovery_prefix: homeassistant
```

#### Inverter sections

Each inverter on the RS485 bus gets its own entry under `inverters:`.
Multiple inverters are polled sequentially on the shared bus.

```yaml
inverters:
  - id: 1                          # RS485 address (default: 1)
    name: StecaGrid 3600           # friendly name (shown in HA, logs)
    topic: DS18/PV/StecaGrid_3600  # MQTT base topic
    values_of_interest:
      - CURRENT_ELECTRICITY_DELIVERY   # AC output power (W)
      - ELECTRICITY_EXPORTED_TOTAL     # Total lifetime yield (Wh)
      - CURRENT_DAILY_YIELD            # Today's yield (Wh)
      - CURRENT_PANEL_POWER            # DC panel power (W)
      - CURRENT_PANEL_VOLTAGE          # DC panel voltage (V)
      - CURRENT_PANEL_CURRENT          # DC panel current (A)
      - SG_SERIAL                      # Serial number (string)

  # Second inverter at a different RS485 address:
  # - id: 2
  #   name: StecaGrid 3600 (Garage)
  #   topic: DS18/PV/StecaGrid_3600_Garage
  #   values_of_interest:
  #     - CURRENT_ELECTRICITY_DELIVERY
  #     - ELECTRICITY_EXPORTED_TOTAL
  #     - CURRENT_DAILY_YIELD
```

> **Backward compatibility** — the old flat `topic` / `values_of_interest` keys are still
> accepted; they are treated as a single inverter at id=1.

### Running

```bash
python3 steca_mqtt.py
python3 steca_mqtt.py -v                        # verbose output
python3 steca_mqtt.py -v -c /etc/steca/config.yaml
```

### MQTT topics (per inverter)

| Topic | Direction | Content |
|-------|-----------|---------|
| `<topic>/CURRENT_ELECTRICITY_DELIVERY` | Publish | AC power (W) |
| `<topic>/ELECTRICITY_EXPORTED_TOTAL` | Publish | Total yield (Wh) |
| `<topic>/CURRENT_DAILY_YIELD` | Publish | Today's yield (Wh) |
| `<topic>/CURRENT_PANEL_POWER` | Publish | Panel power (W) |
| `<topic>/CURRENT_PANEL_VOLTAGE` | Publish | Panel voltage (V) |
| `<topic>/CURRENT_PANEL_CURRENT` | Publish | Panel current (A) |
| `<topic>/SG_SERIAL` | Publish | Serial number |
| `<topic>/setpoint/power_limit_percent` | **Subscribe** | Power limit (0.0–100.0 %) |
| `<topic>/setpoint/power_limit_percent/state` | Publish | Current setpoint (retained) |

### Power-limit setpoint

Send a float payload (0.0–100.0) to `<topic>/setpoint/power_limit_percent`:

```bash
# Throttle to 60 %
mosquitto_pub -t DS18/PV/StecaGrid_3600/setpoint/power_limit_percent -m 60

# Release — restore full power immediately
mosquitto_pub -t DS18/PV/StecaGrid_3600/setpoint/power_limit_percent -m 100
```

**Behaviour:**
- `< 100 %` — setpoint frame is re-sent every poll cycle. The inverter resets its setpoint
  after ~1 min, so continuous repetition is required to maintain throttling.
- `= 100 %` — frame is sent once and repeated until the inverter ACKs `Ok`, then silent.
  The bus stays quiet during normal full-power operation.

Under the hood this uses `steca_setpoint.build_setpoint_percent()` which sends a
`WriteDataById (0x50)` on topic `0x0d` with a 16-bit big-endian permille value.

> **⚠️ Warning** — do not send setpoints while a physical SEM energy manager is
> connected to RS485 address `0x01`. Two-master collision will corrupt frames on the bus.

### Home Assistant autodiscovery

Set `ha_discovery: true` in `config.yaml`. On every MQTT connect the service publishes
retain=True discovery configs. Each inverter appears as a separate HA device.

**Entities created per inverter:**

| Type | Entity | Notes |
|------|--------|-------|
| Sensor | AC Power | `device_class: power`, `state_class: measurement` |
| Sensor | Total Yield | `device_class: energy`, `state_class: total_increasing` |
| Sensor | Daily Yield | `device_class: energy`, `state_class: total_increasing` |
| Sensor | Panel Power | `device_class: power`, `state_class: measurement` |
| Sensor | Panel Voltage | `device_class: voltage`, `state_class: measurement` |
| Sensor | Panel Current | `device_class: current`, `state_class: measurement` |
| Sensor | Serial Number | string, no device_class |
| **Number** | **Power Limit** | 0–100 % slider, wired to the setpoint topic |

Discovery topics follow the pattern:
```
<ha_discovery_prefix>/sensor/<node_id>/<METRIC>/config
<ha_discovery_prefix>/number/<node_id>/power_limit_percent/config
```

---

### Cableing

[![Diagram](https://upload.wikimedia.org/wikipedia/commons/a/ab/StecaGrid_to_Raspberry.svg)](https://commons.wikimedia.org/wiki/File:StecaGrid_to_Raspberry.svg)

---

## StecaGridController.py — Command-line Tool

Reads and writes inverter data via RS485. All frames synthesized by `steca_crc.py`
with verified CRC1 + CRC2.

### Install

```bash
pip3 install pyserial
```

### Usage

```
usage: StecaGridController.py [-h] [-v] [-u] [-s SERIAL] [--id ID]
                               [-np] [-pp] [-pv] [-pc] [-ap] [-gm] [-el]
                               [-dy] [-ty] [-ti] [-sn] [-ve]
                               [--bootup-timestamp]
                               [--10min-history [N]] [--daily-history [N]]
                               [--monthly-history [N]] [--yearly-history]
                               [--discover] [--full-scan]
                               [--set-time DATETIME] [--sync-time] [--DST]
                               [--setpoint PERMILLE] [--setpoint-percent PERCENT]

Read options:
  -ap   AC power (W)
  -dy   Daily yield (Wh)
  -ty   Total yield (Wh)
  -pp   Panel power (W)
  -pv   Panel voltage (V)
  -pc   Panel current (A)
  -np   Nominal power (W)
  -ti   Inverter time
  -sn   Serial number
  -ve   Firmware versions
  -gm   Grid measurements (ENS1 + ENS2)
  -el   Event log (both pages)
  --bootup-timestamp   Inverter boot time (topic 0x08)

Historical yield (UploadById, index 0 = most recent):
  --10min-history [N]    10-minute power curve (0=today, max 30)
  --daily-history [N]    Daily yield totals for month (0=this month, max 12)
  --monthly-history [N]  Monthly yield totals for year (0=this year, max 19)
  --yearly-history       All yearly yield totals

Discovery:
  --discover    Scan RS485 bus (IDs 0x01..0x0a)
  --full-scan   With --discover: scan 0x01..0x65

Clock:
  --set-time DATETIME   Set inverter clock ("YYYY-MM-DD HH:MM:SS").
                        The Steca has no DST — pass standard/winter time by default.
  --sync-time           Sync inverter clock to system time.
                        Subtracts 1 h during DST season unless --DST.
  --DST                 Use with --set-time / --sync-time: send summer/DST time
                        instead of converting to standard/winter time.

Write / control:
  --setpoint PERMILLE
      Send active-power setpoint in permille (0..1000) directly to inverter.
      WARNING: do not use with physical SEM on bus; repeat periodically.
  --setpoint-percent PERCENT
      Like --setpoint but in percent (0.0..100.0, 0.1 % resolution).
```

### Examples

```bash
$ python3 StecaGridController.py -ty -u
52978840.0 Wh

$ python3 StecaGridController.py --bootup-timestamp
Boot time: 2026-05-13 05:30:12  (24048000 ms uptime)

$ python3 StecaGridController.py --sync-time
Syncing inverter clock to 2026-05-14 21:30:00 (DST active → converted to standard/winter time)
OK
Inverter time: 2026-05-14 21:30:01

$ python3 StecaGridController.py --sync-time --DST
Syncing inverter clock to 2026-05-14 22:30:00 (DST mode — using local/summer time)
OK
Inverter time: 2026-05-14 22:30:01

$ python3 StecaGridController.py --10min-history
10-min history: 2026-05-14  (today)
──────────────────────────────────
  06:20         6 Wh
  06:30        12 Wh
  ...
  21:40        18 Wh
──────────────────────────────────
  Total:    8,169 Wh

$ python3 StecaGridController.py --yearly-history
Yearly history
──────────────────────
  2014    9,500,000 Wh
  2015   12,300,000 Wh
  ...
  2026       32,300 Wh
──────────────────────
  Total  154,132,300 Wh

$ python3 StecaGridController.py --discover --full-scan
StecaGrid RS485 Bus Discovery
  Scanning: 101 IDs (0x01..0x65)
  0x01  ✓ found  Serial: XXXXXXXXXXXXXXXXXXXX
Result: 1 inverter(s) on bus.
```

### Write ACK response codes

All write operations (`0x50`/`0x60`) return a status byte:

| Code | Name |
|------|------|
| `0x00` | Ok |
| `0x01` | ServiceNotSupported |
| `0x02` | RequestOutOfRange |
| `0x08` | NoCorrectRequest |
| `0x09` | Busy |
| `0x0a` | ReceivedDataInvalid |
| `0x0f` | NoResponse |
| `0x10` | Error |

---

## Protocol Reference

A proprietary request/response protocol over RS485, used by the StecaGrid SEM energy manager
to communicate with StecaGrid inverters. Newer inverter models have an XML/HTTP API instead.

### Serial Parameters

| Parameter | Value |
|-----------|-------|
| Baudrate  | **38400** |
| Data bits | 8 |
| Parity    | None |
| Stop bits | 1 |
| Connector | RJ45 (RS485 A/B/GND, **not** Ethernet) |

### RS485 Addresses

| Address | Device |
|---------|--------|
| `0x01`  | Inverter (default) |
| `0x7b`  | SEM sender ID used by this tool |
| `0xc9`  | StecaGrid User 4.4 (SEM software) |
| `0x65`  | StecaGrid SEM energy manager hardware |

### Frame Structure

```
[02] [01] [00] [LEN] [TO] [FROM] [CRC1] [payload...] [CRC2_HI] [CRC2_LO] [03]
  0    1    2    3    4     5      6       7 .. -4       -3         -2      -1

LEN = total frame length including STX (0x02) and ETX (0x03)
```
- **STX** `0x02`, **ETX** `0x03`
- **LEN** big-endian uint16 at bytes [2:4] = total frame length
- **TO / FROM** RS485 device IDs
- **CRC1** covers bytes `[0:6]` — see [CRC section](#crc)
- **CRC2** is the last 2 bytes before ETX — see [CRC section](#crc)
- **Payload** starts at byte 7: `[cmd, auth, dlen_hi, dlen_lo, topic, data..., chk]`
  - `auth` = authorization level byte (`0x03` = Administrator)
  - `dlen` = length of `[topic, data...]` before `chk`
  - `chk` = `(0x55 + sum([topic, data...])) & 0xFF`

### Service Code Table

| Request | Name                   | Response |
|---------|------------------------|----------|
| `0x11`  | Reset                  | —        |
| `0x20`  | ReadIdentification     | `0x21`   |
| `0x22`  | ReadDiagnosticServices | `0x23`   |
| `0x30`  | ReadErrorBuffer        | `0x31`   |
| `0x32`  | ReadErrorBufferEnvData | `0x33`   |
| `0x34`  | ClearErrorBuffer       | `0x35`   |
| `0x40`  | ReadDataById           | `0x41`   |
| `0x50`  | WriteDataById          | `0x51`   |
| `0x54`  | GetDataById            | `0x55`   |
| `0x60`  | DownloadById           | `0x61`   |
| `0x64`  | UploadById             | `0x65`   |
| `0x68`  | UploadInternById       | `0x69`   |
| `0x70`  | BootloaderConnect      | `0x71`   |

### Authorization Levels

`0`=User, `1`=Service, `2`=Development, `3`=Administrator.
The software operates at Administrator level by default.

### Topic Map

#### Inverter reads (TO=`0x01`)

| Topic  | Service       | Content                                      |
|--------|---------------|----------------------------------------------|
| `0x05` | Upload (R/W)  | Time (`YY MM DD HH MM SS`, year offset 2000) |
| `0x08` | Upload        | Bootup timestamp (ms since boot, BE uint32)  |
| `0x09` | UploadIntern  | Serial number (ASCII)                        |
| `0x1d` | Read          | Nominal power                                |
| `0x22` | Read          | Panel power (DC)                             |
| `0x23` | Read          | Panel voltage (DC)                           |
| `0x24` | Read          | Panel current (DC)                           |
| `0x29` | Read          | AC power                                     |
| `0x32` | Get           | Country code                                 |
| `0x33` | Get           | Country code list                            |
| `0x3c` | Read          | Daily yield                                  |
| `0x51` | Read          | Grid measurements ENS1+ENS2                 |
| `0x52` | Read          | Grid measurements L2                         |
| `0x53` | Read          | Grid measurements L3                         |
| `0x5a` | UploadIntern  | Event log page 1 (~860 B, up to 20 entries)  |
| `0x5b` | UploadIntern  | Event log page 2 (most recent entries)       |
| `0xef` | Upload        | All yearly yields (float array)              |
| `0xf1` | Upload (R/W)  | Total yield (IEEE 754 LE float, Wh)          |

#### Historical yield — all UploadById (`0x64`), TO=`0x01`

Index 0 = most recent period, index N = N periods ago.

| Series       | Count | Topic IDs | Index 0 |
|--------------|-------|-----------|---------|
| DayCurves    | 31    | `0x7b, 0x75, 0x6f, 0x69, 0x63, 0x5d, 0x57,` then `0x93`..`0x7c` | today |
| DayValues    | 13    | `0xbf, 0xbd, 0xbb, 0xb9, 0xb7, 0xb5, 0xb3, 0xb1, 0xaf, 0xad, 0xab, 0xa9, 0xa8` | this month |
| MonthValues  | 20    | `0xe0`..`0xcd` (descending) | this year |
| YearValues   | 1     | `0xef` | all years |

#### SEM reads/writes (TO=`0x65`)

| Topic  | Service       | Content                          |
|--------|---------------|----------------------------------|
| `0x0a` | Upload (R/W)  | EnergyManager config (~87 bytes) |
| `0x0b` | Upload        | Relais history                   |
| `0x0d` | Upload        | EnergyManager live measurements  |

### Write Operations

#### Direct to inverter (TO=`0x01`)

| Cmd    | Topic  | Data                     | Effect                     |
|--------|--------|--------------------------|----------------------------|
| `0x11` | —      | (no payload)             | Reset inverter             |
| `0x50` | `0x01` | `uint32 = 0x55555555`    | Factory reset ⚠️           |
| `0x50` | `0x0b` | `uint32 = countryCode`   | Set country code           |
| `0x50` | `0x0b` | `uint32 = 0xFFFF`        | Delete country code        |
| `0x50` | `0xff` | `uint32 = newAddr`       | Set inverter RS485 address |
| `0x60` | `0x05` | `[YY MM DD HH MM SS]`    | Set time                   |
| `0x60` | `0xf1` | `float32_LE × 1000`      | Set total yield            |

#### Active-power setpoint

Write(0x50) on Topic `0x0d`, TO=`0x01`, FROM=`0x7b`.
Verified against live hardware across all four relay levels.

**Permille encoding** — 16-bit big-endian, 0..1000 (= 0.0 %..100.0 %, 0.1 % resolution):

| Relay | Percent | Permille | `<hi> <lo>` |
|-------|---------|----------|-------------|
| K1    | 0 %     | 0        | `00 00`     |
| K2    | 30 %    | 300      | `01 2C`     |
| K3    | 60 %    | 600      | `02 58`     |
| K4    | 100 %   | 1000     | `03 E8`     |

Frame body (between CRC1 and CRC2):
```
50 03 00 05 0d 00 ff <hi> <lo> <chk>
chk = (0x50 + 0x05 + 0x0D + 0x00 + 0xFF + hi + lo) & 0xFF
```

```python
from steca_setpoint import build_setpoint, build_setpoint_percent
frame = build_setpoint(300)           # 30 %
frame = build_setpoint_percent(60.0)  # 60 %
```

### Data Encoding

**Steca proprietary float** (4 bytes: `[unit, b1, b2, b3]`):
```python
iacpower = ((b3 << 8 | b1) << 8 | b2) << 7
value, = struct.unpack('f', struct.pack('I', iacpower & 0xFFFFFFFF))
```
Unit byte: `0x05`=V, `0x07`=A, `0x09`=Wh, `0x0B`=W, `0x0D`=Hz, `0x00`=NUL

**Total Yield** (4 bytes little-endian IEEE 754 float, Wh):
```python
bits = b[3]<<24 | b[2]<<16 | b[1]<<8 | b[0]
value, = struct.unpack('f', struct.pack('I', bits))
```

### CRC

Both CRC algorithms use a **nibble-based lookup table** (not standard polynomials).
Solved by combining passive RS485 sniffing with cross-referencing
[MichaelOE/homeassistant-stecagrid](https://github.com/MichaelOE/homeassistant-stecagrid/blob/main/custom_components/stecagrid/steca.py).

```python
CRC8_TABLE  = [0x00, 0x8F, 0x27, 0xA8, 0x4E, 0xC1, 0x69, 0xE6,
               0x9C, 0x13, 0xBB, 0x34, 0xD2, 0x5D, 0xF5, 0x7A]
CRC16_TABLE = [0x0000, 0xACAC, 0xEC05, 0x40A9, 0x6D57, 0xC1FB, 0x8152, 0x2DFE,
               0xDAEA, 0x7602, 0x36AB, 0x9A07, 0xB7F9, 0x1B55, 0x5BFC, 0xF750]

# CRC1: covers frame bytes [0:6]
crc1 = crc8_nibble(frame[0:6], init=0x55)

# CRC2: covers entire frame excluding the two CRC2 bytes, including ETX
crc2 = crc16_nibble(frame[:-3] + b'\x03', init=0x5555)
```

Verified against all frame types: ping, read (`0x40`/`0x64`/`0x68`),
write (`0x34`/`0x50`/`0x60`), and responses.

### Captured Reference Frames (SEM=`0x7b`, inverter=`0x01`)

```python
SG_VERSIONS      = bytes.fromhex("0201000c017bc62003798c03")
SG_NOMINAL_POWER = bytes.fromhex("02010010017bb5400300011d72309503")
SG_PANEL_POWER   = bytes.fromhex("02010010017bb540030001227712ee03")
SG_PANEL_VOLTAGE = bytes.fromhex("02010010017bb540030001237878e403")
SG_PANEL_CURRENT = bytes.fromhex("02010010017bb5400300012479a0b603")
SG_AC_POWER      = bytes.fromhex("02010010017bb540030001297e985b03")
SG_DAILY_YIELD   = bytes.fromhex("02010010017bb5400300013c91e1c903")
SG_TIME          = bytes.fromhex("02010010017bb564030001055a3a4403")
SG_SERIAL        = bytes.fromhex("02010010017bb564030001095e856e03")
SG_TOTAL_YIELD   = bytes.fromhex("02010010017bb564030001f146cc7903")
```

---

## steca_sniffer.py — Passive Bus Sniffer

Monitors all RS485 traffic between the StecaGrid User software and the inverter
without interfering with the bus.

**Features:**
- CRC1 and CRC2 verification for all frame types (nibble-table)
- Decodes all known read responses: GridMeasurements, EventLog, BootupTimestamp
- Decodes write operations: `0x50` WriteDataById, `0x60` DownloadById (SetTime, EMConfig)
- Decodes EnergyManager config reads/writes (SEM address `0x65`)
- Decodes historical yield responses with slot summaries
- JSON log for offline analysis
- Threaded UART reader (no frame loss at 38400 baud)

### Install

```bash
pip3 install pyserial
```

### Usage

```bash
python3 steca_sniffer.py --port /dev/ttyUSB0
python3 steca_sniffer.py --port /dev/ttyUSB0 --verbose
python3 steca_sniffer.py --port /dev/ttyUSB0 --no-log
```

### Example output

```
[00:06:27] RESPONSE  TO=0xc9 FROM=0x01  LEN=860  StecaUser-4.4
  Topic:   0x5a EventLog_p1
  CRC1:0x01[✓]  CRC2:0x0024[✓]  model=nibble_crc16
  → event_log(p1): 74 total, 20 entries

[00:07:01] →SEM  TO=0x65 FROM=0x7b  LEN=103  SEM-7b
  Topic:   0x0a EMConfig
  CRC1:0xe3[✓]  CRC2:0x1a2b[✓]  model=nibble_crc16
  → SetEMConfig mode=PowerLimit(2) limit=2000W nominal=3600W
```

---

## Based on Versions

Tested with the following firmware. Your mileage may vary.
```
StecaGrid 3600  Serial: XXXXXXXXXXXXXXXXXXXX

HMI BFAPI   5.0.0   19.03.2013 14:38:59
HMI FBL     2.0.3   05.04.2013 11:46:20
HMI APP     15.0.0  26.07.2013 13:19:06
HMI PAR     0.0.1   26.07.2013 13:19:06
HMI OEM     0.0.1   11.06.2013 08:11:29
PU BFAPI    5.0.0   19.03.2013_14:38:42
PU FBL      1.0.1   19.12.2012_16:36:04
PU APP      4.0.0   03.05.2013_09:37:55
PU PAR      3.0.0   31.01.2013_13:47:24
ENS1 BFAPI  5.0.0   19.03.2013_14:38:51
ENS1 FBL    1.0.1   19.12.2012_16:34:47
ENS1 APP    39.0.0  11.07.2013_14:39:50
ENS1 PAR    0.0.14  11.07.2013_14:40:03
ENS2 BFAPI  5.0.0   19.03.2013_14:38:51
ENS2 FBL    1.0.1   19.12.2012_16:34:47
ENS2 APP    39.0.0  11.07.2013_14:39:50
ENS2 PAR    0.0.14  11.07.2013_14:40:03
HMI / PU / ENS2 — Net11
```

---

## Disclaimer

Ich übernehme keine Garantie oder Gewährleistung für die Nutzung dieser Software.
Verwendung auf eigene Gefahr.
