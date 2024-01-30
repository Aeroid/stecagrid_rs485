# StecaGrid 3600 RS485 Tools

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
