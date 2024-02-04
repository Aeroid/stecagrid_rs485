# StecaGrid 3600 RS485 Tools

## The protocol

As far as I can tell its a s simple request and response protocol taht Steca had implemented to talk to StecaGrid inverters (around 2013 time frame). Newer models seem to have a better XML API.
- A dynamic datagram structure is used, which starts with 0x02 and ends with 0x03.
- The second data word holds the overall length of the datagram.
- Following that the RS485 id of the recipent and of the sender are always present.
- The next byte (as well as the last word before 0x03) are obviously some CRC.
- The rest (payload) of the datagram depends on the topic and if its the request or response for it
- It typically has a header (requests start with 0x40, 0x64, 0x20, ... responses start with 0x41, 0x65, 0x21, ... respectively)
- The topics are represented in th fifth byte of the payload of both the request and the reponse. A few of the discovered topics are:
  - Grid voltage = L1 MeasurementValues ENS1 (measurement 1/2, value 1/4)
  - Grid power = AC Power (0x29)
  - Grid frequency = L1 MeasurementValues ENS1 (measurement 2/2, value 2/4)
  - Panel voltage (0x23)
  - Panel current (0x24)
  - Panel power (0x22)
  - Daily yield (0x3c)
  - Total yield = ?
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
- Total yield: assumed to be part of msg topics 0xf1 or 0x08 of the 0x65 response group. Both contain five byte data that could not be decoded, yet.

### Examples 

StecaRS485protocol.py can used to explore, discover and decode the datagrams via an RS485 interface. Plenty of recorded data is part of it for replay.

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

### install
    pip3 install pyserial

### Orginal Disclaimer
Ich übernehme keine Garantie oder Gewährleistung für die Nutzung dieser Software-
Verwendung auf eigne Gefahr.

### Example (Debug)
	python3 getStecaGridData.py
	{'baudrate': 38400, 'bytesize': 8, 'parity': 'N', 'stopbits': 1, 'xonxoff': 0, 'dsrdtr': False, 'rtscts': 0, 'timeout': 1, 'write_timeout': None, 'inter_byte_timeout': None}
	serial write [2, 1, 0, 16, 1, 201, 101, 64, 3, 0, 1, 41, 126, 41, 190, 3]
	ser read b'\x02\x01\x00\x1e\xc9\x01`A\x00\x00\x0f)\x00\x00\x07ACPower\x0b><\x88#fZ\x03'
	0 2  0x02
	1 1  0x01
	2 0  0x00
	3 30  0x1e
	4 201 É 0xc9
	5 1  0x01
	6 96 ` 0x60
	7 65 A 0x41
	8 0  0x00
	9 0  0x00
	10 15  0x0f
	11 41 ) 0x29
	12 0  0x00
	13 0  0x00
	14 7  0x07
	15 65 A 0x41
	16 67 C 0x43
	17 80 P 0x50
	18 111 o 0x6f
	19 119 w 0x77
	20 101 e 0x65
	21 114 r 0x72
	22 11
		   0x0b
	23 62 > 0x3e
	24 60 < 0x3c
	25 136 � 0x88
	26 35 # 0x23
	27 102 f 0x66
	28 90 Z 0x5a
	29 3  0x03
	iacpower 0x441F1E00
	iacpower 1142889984
	in_data[24-27] 0x3e3c88
	AC Power: 636.46875
	636.46875
