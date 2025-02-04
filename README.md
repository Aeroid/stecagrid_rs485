# StecaGrid 3600 RS485 Tools

## The protocol

As far as I can tell its a s simple request and response protocol that Steca had implemented to talk to StecaGrid inverters (around 2013 time frame). Newer models seem to have a better XML API.
- A dynamic datagram structure is used, which starts with 0x02 and ends with 0x03.
- The second data word holds the overall length of the datagram.
- Following that the RS485 id of the recipient and of the sender are always present.
- The next byte (as well as the last word before 0x03) are obviously some CRC.
- The rest (payload) of the datagram depends on the topic and if its the request or response for it
- It typically has a header (requests start with 0x40, 0x64, 0x20, ... responses start with 0x41, 0x65, 0x21, ... respectively)
- The topics are represented in the fifth byte of the payload of both the request and the reponse. A few of the discovered topics are:
  - Grid voltage = L1 MeasurementValues ENS1 (measurement 1/2, value 1/4)
  - Grid power = AC Power (0x29)
  - Grid frequency = L1 MeasurementValues ENS1 (measurement 2/2, value 2/4)
  - Panel voltage (0x23)
  - Panel current (0x24)
  - Panel power (0x22)
  - Daily yield (0x3c)
  - Total yield = (0xf1)
  - Time (0x05)
- Data is respresented as Pascal-type strings (pre-fixed by their length as a 16-bit word), proprietary 3-byte floats (pre-fixed by a unit byte) in the payload. Pre-fixed length field are used here and there. Unit prefixes are:
  - V (0x05)
  - A (0x07)
  - Wh (0x09)
  - W (0x0B)
  - Hz (0x0D)
  - NUL (0x00) (some fields switch to this unit type when they fall to zero)
 
### To Do
- CRC: without the CRC calculation no datagram can be synthesized.

### Examples 

StecaRS485protocol.py can be used to explore, discover and decode the datagrams via an RS485 interface. Plenty of recorded data is part of it for replay.

Daily Yield dialog led by StecaGridSEM #123/0x7d with Inverter #1

        hx += bytes.fromhex("03 00 01 3c 91 e1 c9 03 02 01 00 14 7b 01 43 41") # ...<........{.CA
        # 02 01 00 10 01 7b b5 40 03 00 01 3c 91 e1 c9 03
        # dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: e1c9
        # payload: 40 03 00 01 3c 91    @...<.
        # RequestA for 0x3c (Daily Yield) from 1

        hx += bytes.fromhex("00 00 05 3c 09 5f 80 88 01 ab 5a 03 02 01 00 10") # ...<._....Z.....
        # 02 01 00 14 7b 01 43 41 00 00 05 3c 09 5f 80 88 01 ab 5a 03
        # dgram: to: 123  from: 1  len: 20  crc1: 43  crc2: ab5a
        # payload: 41 00 00 05 3c 09 5f 80 88 01    A...<._...
        # ReponseA for 0x3c from 123 len=5
        # Daily Yield 703.00 Wh

Date/Time dialog led by StecaGridSEM #123/0x7d with Inverter #1

        hx += bytes.fromhex("02 01 00 10 01 7b b5 64 03 00 01 05 5a 3a 44 03") # .....{.d....Z:D.
        # 02 01 00 10 01 7b b5 64 03 00 01 05 5a 3a 44 03
        # dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: 3a44
        # payload: 64 03 00 01 05 5a    d....Z
        # RequestB for 0x05 from 1

        hx += bytes.fromhex("02 01 00 17 7b 01 56 65 00 00 08 05 18 02 03 17") # ....{.Ve........
        hx += bytes.fromhex("08 33 01 ca 16 f0 03 02 01 00 10 01 7b b5 64 03") # .3..........{.d.
        # 02 01 00 17 7b 01 56 65 00 00 08 05 18 02 03 17 08 33 01 ca 16 f0 03
        # dgram: to: 123  from: 1  len: 23  crc1: 56  crc2: 16f0
        # payload: 65 00 00 08 05 18 02 03 17 08 33 01 ca    e.........3..
        # ReponseB for 0x05 from 123
        # 03.02.24 23:08:51 ( 18 02 03 17 08 33 01 ca 16 )

## getStecaGridData.py

Simple bare metal RS485 proof of concept code that requests ACPower via RS485 and outputs plain float value (Watts).

### Install
    pip3 install pyserial

### Usage
        usage: getStecaGridData.py [-h] [-v] [-u] [-s SERIAL] [-np] [-pp] [-pv] [-pc] [-ve] [-sn] [-ti] [-dy] [-ty] [-ap]

        Read data via RS485 from StecaGrid3600

        optional arguments:
          -h, --help            show this help message and exit
          -v, --verbose         Enable verbose output
          -u, --unit            output unit of measurement
          -s SERIAL, --serial SERIAL
                                Serial interface for RS485 communication (default /dev/ttyS0)
          -np, --nominal_power  request nominal_power
          -pp, --panel_power    request panel_power
          -pv, --panel_voltage  request panel_voltage
          -pc, --panel_current  request panel_current
          -ve, --versions       request versions
          -sn, --serialnumber   request serial number
          -ti, --time           request time
          -dy, --daily_yield    request daily_yield
          -ty, --total_yield    request total_yield
          -ap, --ac_power       request ac_power

### Orginal Disclaimer
Ich übernehme keine Garantie oder Gewährleistung für die Nutzung dieser Software-
Verwendung auf eigne Gefahr.

### Example (Debug)
        python3 getStecaGridData.py -v -u --total_yield
        {'baudrate': 38400, 'bytesize': 8, 'parity': 'N', 'stopbits': 1, 'xonxoff': 0, 'dsrdtr': False, 'rtscts': 0, 'timeout': 1, 'write_timeout': None, 'inter_byte_timeout': None}

        serial write:
        # 02 01 00 10 01 7b b5 64 03 00 01 f1 46 cc 79 03
        # dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: cc79
        # payload: 64 03 00 01 f1 46    d....F
        # RequestB for 0xf1 from 1
        [1, 123, 100, 241]

        serial read:
        # 02 01 00 14 7b 01 43 65 00 00 05 f1 7c 58 24 4c 8a 1b ef 03
        # dgram: to: 123  from: 1  len: 20  crc1: 43  crc2: 1bef
        # payload: 65 00 00 05 f1 7c 58 24 4c 8a    e....|X$L.
        # ReponseB for 0xf1 from 123
        # ( 7c 58 24 4c 8a )
        # [43082224.0, 'Wh']
        [123, 1, 101, 241, 'Total Yield', [43082224.0, 'Wh']]
        43082224.0 Wh

### Further Requests for replay approach
The following telegrams are requests to extend the replay beyond AC Power. Note, that they all address the inverter with the RS485 ID #1. You will have to change your Steca to that ID until we have figured out the CRC generation to synthesize a full new telegram for a different id. Contact me of you need a replay telegram for a differnt ID, and I might be able to record one for you from the SEM.

        SG_NOMINAL_POWER = bytes.fromhex("02 01 00 10 01 7b b5 40 03 00 01 1d 72 30 95 03")
        SG_PANEL_POWER   = bytes.fromhex("02 01 00 10 01 7b b5 40 03 00 01 22 77 12 ee 03")
        SG_PANEL_VOLTAGE = bytes.fromhex("02 01 00 10 01 7b b5 40 03 00 01 23 78 78 e4 03")
        SG_PANEL_CURRENT = bytes.fromhex("02 01 00 10 01 7b b5 40 03 00 01 24 79 a0 b6 03")
        SG_VERSIONS      = bytes.fromhex("02 01 00 0c 01 7b c6 20 03 79 8c 03")
        SG_SERIAL        = bytes.fromhex("02 01 00 10 01 7b b5 64 03 00 01 09 5e 85 6e 03")
        SG_TIME          = bytes.fromhex("02 01 00 10 01 7b b5 64 03 00 01 05 5a 3a 44 03")
        SG_DAILY_YIELD   = bytes.fromhex("02 01 00 10 01 7b b5 40 03 00 01 3c 91 e1 c9 03")
        SG_TOTAL_YIELD   = bytes.fromhex("02 01 00 10 01 7b b5 64 03 00 01 f1 46 cc 79 03")
        SG_AC_POWER      = bytes.fromhex("02 01 00 10 01 7b b5 40 03 00 01 29 7e 98 5b 03")

### Based on versions
All of my tinkering is based on the following firmware versions. You milage may vary.

		python3 getStecaGridData.py -ve

		StecaGrid 3600

		HMI BFAPI       5.0.0   19.03.2013 14:38:59
		HMI FBL         2.0.3   05.04.2013 11:46:20
		HMI APP         15.0.0  26.07.2013 13:19:06
		HMI PAR         0.0.1   26.07.2013 13:19:06
		HMI OEM         0.0.1   11.06.2013 08:11:29
		PU BFAPI        5.0.0   19.03.2013_14:38:42
		PU FBL  1.0.1   19.12.2012_16:36:04
		PU APP  4.0.0   03.05.2013_09:37:55
		PU PAR  3.0.0   31.01.2013_13:47:24
		ENS1 BFAPI      5.0.0   19.03.2013_14:38:51
		ENS1 FBL        1.0.1   19.12.2012_16:34:47
		ENS1 APP        39.0.0  11.07.2013_14:39:50
		ENS1 PAR        0.0.14  11.07.2013_14:40:03
		ENS2 BFAPI      5.0.0   19.03.2013_14:38:51
		ENS2 FBL        1.0.1   19.12.2012_16:34:47
		ENS2 APP        39.0.0  11.07.2013_14:39:50
		ENS2 PAR        0.0.14  11.07.2013_14:40:03
		HMI     PU      ENS2
		Net11
