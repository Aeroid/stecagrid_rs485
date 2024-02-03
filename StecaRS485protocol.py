import serial
import time
import binascii
import struct
from ctypes import c_ushort

bauds = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 500000, 576000, 921600, 1000000, 1152000, 1500000, 2000000, 2500000, 3000000, 3500000, 4000000, 50, 75, 110, 134, 150, 200, 300, 600, 1200, 1800, 2400, 4800];

if __name__ == '__main__':
    # https://pythonhosted.org/pyserial/pyserial_api.html
    ser = serial.Serial(    
        port='/dev/ttyS0',
        baudrate=38400,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.3
    ) 
    ser.flush()
    br = 0;

#settings = ser.get_settings()
#print(settings)

def dump_bytes(formatted_hex_bytes, printable):
    print("# ",formatted_hex_bytes)
    print("# ",printable)
    print()

def process_telegram(t):
    process_steca485(t)
    formatted_hex_bytes = format_hex_bytes(t)
    printable = format_printable(t)
    print()    
    #dump_bytes(formatted_hex_bytes, printable)
   
def decode_stecaFloat(ac_bytes):
    if ac_bytes[0] == 0x0B:
        unit = "W"
    elif ac_bytes[0] == 0x07:
        unit = "A"
    elif ac_bytes[0] == 0x05:
        unit = "V"
    elif ac_bytes[0] == 0x0D:
        unit = "Hz"
    elif ac_bytes[0] == 0x09:
        unit = "Wh"
    elif ac_bytes[0] == 0x00:
        unit = "NUL"
    else:
        unit = f'0x{ac_bytes[0]:02x}'

    iacpower = ((ac_bytes[3] << 8 | ac_bytes[1]) << 8 | ac_bytes[2]) << 7 # formula to float - conversion according to Steca
    facpower, = struct.unpack('f', struct.pack('I', iacpower))

    #if DEBUG:
    #print("# i: 0x%0X" % iacpower,"=", str(iacpower))
    #print("# f:", facpower)

    return f"{facpower:0.2f} {unit}"

# Grid voltage = L1 MeasurementValues ENS1 (measurement 1/2, value 1/4)
# Grid power = AC Power
# Grid frequency = L1 MeasurementValues ENS1 (measurement 2/2, value 2/4)
# Panel voltage 
# Panel current 
# Panel power 
# Daily yield 
# Total yield = ?
# Time

def process_steca485(t):
    if is_one_full_telegram(t):
        print("#",format_hex_bytes(t))
        print("# dgram:","",end="")
#        print("# ",t[4:-1])
#        print("start:",t[0]," ",end="")
        print("to:",t[4]," ",end="")
        print("from:",t[5]," ",end="")
        print("len:",(t[2] << 8 | t[3])," ",end="")
        print(f"crc1: {t[6]:02x}"," ",end="")
        print(f"crc2: {t[-3]:02x}{t[-2]:02x}"," ",end="")
        print() #        print("stop:",t[-1])
        # Payload started 7
        print("# payload:", format_hex_bytes(t[7:-3]) ,"",end="")
        print("  ", format_printable(t[7:-3]))
        if t[7] == 0x40:
            topic=""
            if t[11] == 0x1d:
                topic = " (Nominal Power)"
            elif t[11] == 0x22:
                topic = " (Panel Power)"
            elif t[11] == 0x23:
                topic = " (Panel Voltage)"
            elif t[11] == 0x24:
                topic = " (Panel Current)"
            elif t[11] == 0x29:
                topic = " (ACPower)"
            elif t[11] == 0x3c:
                topic = " (Daily Yield)"
            print(f"# RequestA for 0x{t[11]:02x}{topic} from {t[4]}")
        elif t[7] == 0x41:
            if t[8] == 0x00:
                len = (t[9] << 8 | t[10])
                print(f"# ReponseA for 0x{t[11]:02x} from {t[4]} len={len}")
                if t[11] == 0x51: # Label Value Value Value Value byte Label Value Value Value Value byte
                    i_labelA = 15
                    i_valA1 = i_labelA + (t[i_labelA-2] << 8 | t[i_labelA-1])
                    i_valA2 = i_valA1+4
                    i_valA3 = i_valA2+4
                    i_valA4 = i_valA3+4
                    #print(i_labelA,t[i_labelA-2],t[i_labelA-1],i_valA1,i_valA2,i_valA3,i_valA4)
                    i_labelB = i_valA4+4+1+2
                    i_valB1 = i_labelB + (t[i_labelB-2] << 8 | t[i_labelB-1])
                    i_valB2 = i_valB1+4
                    i_valB3 = i_valB2+4
                    i_valB4 = i_valB3+4                    
                    #print(i_labelB,t[i_labelB-2],t[i_labelB-1],i_valB1,i_valB2,i_valB3,i_valB4)
                    label = t[15:15+t[14]]
                    print("#", str(t[i_labelA:i_valA1]), 
                        decode_stecaFloat(t[i_valA1:i_valA2]), 
                        decode_stecaFloat(t[i_valA2:i_valA3]), 
                        decode_stecaFloat(t[i_valA3:i_valA4]), 
                        decode_stecaFloat(t[i_valA4:i_valA4+4])) 
                    print("#", str(t[i_labelB:i_valB1]), 
                        decode_stecaFloat(t[i_valB1:i_valB2]), 
                        decode_stecaFloat(t[i_valB2:i_valB3]), 
                        decode_stecaFloat(t[i_valB3:i_valB4]), 
                        decode_stecaFloat(t[i_valB4:i_valB4+4])) 
                elif t[11] == 0x3c:
                    print("# Daily Yield", decode_stecaFloat(t[12:16]))
                else:
                    label = t[15:15+t[14]]
                    print("#", str(label), decode_stecaFloat(t[15+t[14]:15+t[14]+5]))
        elif t[7] == 0x64:
            print(f"# RequestB for 0x{t[11]:02x} from {t[4]}")
        elif t[7] == 0x65:
            print(f"# ReponseB for 0x{t[11]:02x} from {t[4]}")
            if t[11] == 0xF1: #  ???
                print("# (",format_hex_bytes(t[12:17]),")")
                print("#", decode_stecaFloat(t[12:16]))
            if t[11] == 0x05: # Time ???
                print(f"# {t[14]:02}.{t[13]:02}.{t[12]:02} {t[15]:02}:{t[16]:02}:{t[17]:02} (",format_hex_bytes(t[12:21]),")")
            if t[11] == 0x08: #  ???
                print("# (",format_hex_bytes(t[12:17]),")")
                print("#", decode_stecaFloat(t[12:16]))
        elif t[7] == 0x21:
            if t[8] == 0x00:
                len = (t[9] << 8 | t[10])
                print("# ReponseC for", t[11], "from", t[4], "len=",len)

    else:
        print("# NOT a single full Steca485 Telegram")

def format_hex_bytes(b):
    formatted_hex_bytes = ''
    for byte in b:
        hex_byte = f'{byte:02x}'
        formatted_hex_bytes += f'{hex_byte:>2} '
    return formatted_hex_bytes.strip()

def format_printable(b):
    printable = ''
    for byte in b:
        if not 32 <= byte <= 126:
            printable += '.'
        else:
            printable += chr(byte)
    return printable

def xprocess_telegram(t):
    formatted_hex_bytes = format_hex_bytes(t)
    printable = format_printable(t)
    print(f'hx += bytes.fromhex("{formatted_hex_bytes}") # {printable} ')

def split_byte_array(byte_array):
    sub_arrays = []
    start_index = 0
    for i in range(len(byte_array)):
        if byte_array[i] == 0x03 and (i + 1 < len(byte_array) and byte_array[i + 1] == 0x02):
            sub_arrays.append(byte_array[start_index:i+1])
            start_index = i + 1
            break
    if start_index < len(byte_array):
        sub_arrays.append(byte_array[start_index:])
    return sub_arrays

def is_one_full_telegram(t):
    if t[0] != 2:
        #print("not starting w/ 0x02")
        return False
    if t[len(t)-1] != 3:
        #print("not ending w/ 0x03")
        return False
    if len(t) != (t[2] << 8 | t[3]):
        #print("wrong length",len(t), "!=", (t[2] << 8 | t[3]))
        return False
    return True
    
def process_telegrams(t):
    if len(t) == 0:
        return b''
    sub_arrays = split_byte_array(t)
    if len(sub_arrays) > 0:
        if is_one_full_telegram(sub_arrays[0]):
            process_telegram(sub_arrays[0])
        else:
            return sub_arrays[0]
    if len(sub_arrays) > 1:
        return process_telegrams(sub_arrays[1])
    return b''

buffer = b''

hx = b''

##
## Data recorded while pressing Data refesh in the StecaGrid Software
##

hx += bytes.fromhex("02 01 00 10 04 7b bf 40 03 00 01 1d 72 da 81 03") # .....{.@....r...
# 02 01 00 10 04 7b bf 40 03 00 01 1d 72 da 81 03
# dgram: to: 4  from: 123  len: 16  crc1: bf  crc2: da81
# payload: 40 03 00 01 1d 72    @....r
# RequestA for 0x1d (Nominal Power) from 4

hx += bytes.fromhex("02 01 00 10 01 7b b5 40 03 00 01 22 77 12 ee 03") # .....{.@..."w...
# 02 01 00 10 01 7b b5 40 03 00 01 22 77 12 ee 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: 12ee
# payload: 40 03 00 01 22 77    @..."w
# RequestA for 0x22 (Panel Power) from 1

hx += bytes.fromhex("02 01 00 21 7b 01 15 41 00 00 12 22 00 00 0a 50") # ...!{..A..."...P
hx += bytes.fromhex("61 6e 65 6c 50 6f 77 65 72 00 00 01 2d ac 8c 48") # anelPower...-..H
hx += bytes.fromhex("03 02 01 00 10 01 7b b5 40 03 00 01 23 78 78 e4") # ......{.@...#xx.
# 02 01 00 21 7b 01 15 41 00 00 12 22 00 00 0a 50 61 6e 65 6c 50 6f 77 65 72 00 00 01 2d ac 8c 48 03
# dgram: to: 123  from: 1  len: 33  crc1: 15  crc2: 8c48
# payload: 41 00 00 12 22 00 00 0a 50 61 6e 65 6c 50 6f 77 65 72 00 00 01 2d ac    A..."...PanelPower...-.
# ReponseA for 0x22 from 123 len=18
# b'PanelPower' 0.00 NUL

hx += bytes.fromhex("03 02 01 00 23 7b 01 e4 41 00 00 14 23 00 00 0c") # ....#{..A...#...
# 02 01 00 10 01 7b b5 40 03 00 01 23 78 78 e4 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: 78e4
# payload: 40 03 00 01 23 78    @...#x
# RequestA for 0x23 (Panel Voltage) from 1

hx += bytes.fromhex("50 61 6e 65 6c 56 6f 6c 74 61 67 65 05 99 99 7d") # PanelVoltage...}
hx += bytes.fromhex("fa e1 70 03 02 01 00 10 01 7b b5 40 03 00 01 24") # ..p......{.@...$
# 02 01 00 23 7b 01 e4 41 00 00 14 23 00 00 0c 50 61 6e 65 6c 56 6f 6c 74 61 67 65 05 99 99 7d fa e1 70 03
# dgram: to: 123  from: 1  len: 35  crc1: e4  crc2: e170
# payload: 41 00 00 14 23 00 00 0c 50 61 6e 65 6c 56 6f 6c 74 61 67 65 05 99 99 7d fa    A...#...PanelVoltage...}.
# ReponseA for 0x23 from 123 len=20
# b'PanelVoltage' 0.40 V

hx += bytes.fromhex("79 a0 b6 03 02 01 00 23 7b 01 e4 41 00 00 14 24") # y......#{..A...$
# 02 01 00 10 01 7b b5 40 03 00 01 24 79 a0 b6 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: a0b6
# payload: 40 03 00 01 24 79    @...$y
# RequestA for 0x24 (Panel Current) from 1

hx += bytes.fromhex("00 00 0c 50 61 6e 65 6c 43 75 72 72 65 6e 74 00") # ...PanelCurrent.
hx += bytes.fromhex("00 01 2d 86 ae 7f 03 02 01 00 10 01 7b b5 40 03") # ..-.........{.@.
# 02 01 00 23 7b 01 e4 41 00 00 14 24 00 00 0c 50 61 6e 65 6c 43 75 72 72 65 6e 74 00 00 01 2d 86 ae 7f 03
# dgram: to: 123  from: 1  len: 35  crc1: e4  crc2: ae7f
# payload: 41 00 00 14 24 00 00 0c 50 61 6e 65 6c 43 75 72 72 65 6e 74 00 00 01 2d 86    A...$...PanelCurrent...-.
# ReponseA for 0x24 from 123 len=20
# b'PanelCurrent' 0.00 NUL

hx += bytes.fromhex("00 01 29 7e 98 5b 03 02 01 00 1e 7b 01 3d 41 00") # ..)~.[.....{.=A.
# 02 01 00 10 01 7b b5 40 03 00 01 29 7e 98 5b 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: 985b
# payload: 40 03 00 01 29 7e    @...)~
# RequestA for 0x29 (ACPower) from 1

hx += bytes.fromhex("00 0f 29 00 00 07 41 43 50 6f 77 65 72 00 00 01") # ..)...ACPower...
hx += bytes.fromhex("2d 44 7b b1 03 02 01 00 10 01 7b b5 40 03 00 01") # -D{.......{.@...
# 02 01 00 1e 7b 01 3d 41 00 00 0f 29 00 00 07 41 43 50 6f 77 65 72 00 00 01 2d 44 7b b1 03
# dgram: to: 123  from: 1  len: 30  crc1: 3d  crc2: 7bb1
# payload: 41 00 00 0f 29 00 00 07 41 43 50 6f 77 65 72 00 00 01 2d 44    A...)...ACPower...-D
# ReponseA for 0x29 from 123 len=15
# b'ACPower' 0.00 NUL

hx += bytes.fromhex("51 a6 d4 c0 03") # Q....
# 02 01 00 10 01 7b b5 40 03 00 01 51 a6 d4 c0 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: d4c0
# payload: 40 03 00 01 51 a6    @...Q.
# RequestA for 0x51 from 1

hx += bytes.fromhex("02 01 00 0c 7b 01 eb 41 11 26 7c 03") # ....{..A.&|.
# 02 01 00 0c 7b 01 eb 41 11 26 7c 03
# dgram: to: 123  from: 1  len: 12  crc1: eb  crc2: 267c
# payload: 41 11    A.

hx += bytes.fromhex("02 01 00 0c 7b 01 eb 41 11 26 7c 03") # ....{..A.&|.
# 02 01 00 0c 7b 01 eb 41 11 26 7c 03
# dgram: to: 123  from: 1  len: 12  crc1: eb  crc2: 267c
# payload: 41 11    A.

hx += bytes.fromhex("02 01 00 68 7b 01 e2 41 00 00 59 51 00 00 19 4c") # ...h{..A..YQ...L
hx += bytes.fromhex("31 20 4d 65 61 73 75 72 65 6d 65 6e 74 56 61 6c") # 1 MeasurementVal
hx += bytes.fromhex("75 65 73 20 45 4e 53 31 05 dd fb 86 0d 93 10 84") # ues ENS1........
hx += bytes.fromhex("07 00 00 00 05 c8 49 82 00 00 19 4c 31 20 4d 65") # ......I....L1 Me
hx += bytes.fromhex("61 73 75 72 65 6d 65 6e 74 56 61 6c 75 65 73 20") # asurementValues
hx += bytes.fromhex("45 4e 53 32 05 dc f1 86 0d 8c c2 84 07 06 24 77") # ENS2..........$w
hx += bytes.fromhex("05 c8 9b 82 6c e3 9c 03 02 01 00 10 05 7b bd 40") # ....l........{.@
# 02 01 00 68 7b 01 e2 41 00 00 59 51 00 00 19 4c 31 20 4d 65 61 73 75 72 65 6d 65 6e 74 56 61 6c 75 65 73 20 45 4e 53 31 05 dd fb 86 0d 93 10 84 07 00 00 00 05 c8 49 82 00 00 19 4c 31 20 4d 65 61 73 75 72 65 6d 65 6e 74 56 61 6c 75 65 73 20 45 4e 53 32 05 dc f1 86 0d 8c c2 84 07 06 24 77 05 c8 9b 82 6c e3 9c 03
# dgram: to: 123  from: 1  len: 104  crc1: e2  crc2: e39c
# payload: 41 00 00 59 51 00 00 19 4c 31 20 4d 65 61 73 75 72 65 6d 65 6e 74 56 61 6c 75 65 73 20 45 4e 53 31 05 dd fb 86 0d 93 10 84 07 00 00 00 05 c8 49 82 00 00 19 4c 31 20 4d 65 61 73 75 72 65 6d 65 6e 74 56 61 6c 75 65 73 20 45 4e 53 32 05 dc f1 86 0d 8c c2 84 07 06 24 77 05 c8 9b 82 6c    A..YQ...L1 MeasurementValues ENS1..............I....L1 MeasurementValues ENS2..........$w....l
# ReponseA for 0x51 from 123 len=89
# b'L1 MeasurementValues ENS1' 238.99 V 50.38 Hz 0.00 A 14.26 V
# b'L1 MeasurementValues ENS2' 238.47 V 49.59 Hz 0.00 A 14.27 V

hx += bytes.fromhex("03 00 01 1d 72 0f f7 03") # ....r...
# 02 01 00 10 05 7b bd 40 03 00 01 1d 72 0f f7 03
# dgram: to: 5  from: 123  len: 16  crc1: bd  crc2: 0ff7
# payload: 40 03 00 01 1d 72    @....r
# RequestA for 0x1d (Nominal Power) from 5

hx += bytes.fromhex("02 01 00 10 01 7b b5 40 03 00 01 51 a6 d4 c0 03") # .....{.@...Q....
# 02 01 00 10 01 7b b5 40 03 00 01 51 a6 d4 c0 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: d4c0
# payload: 40 03 00 01 51 a6    @...Q.
# RequestA for 0x51 from 1

hx += bytes.fromhex("02 01 00 68 7b 01 e2 41 00 00 59 51 00 00 19 4c") # ...h{..A..YQ...L
hx += bytes.fromhex("31 20 4d 65 61 73 75 72 65 6d 65 6e 74 56 61 6c") # 1 MeasurementVal
hx += bytes.fromhex("75 65 73 20 45 4e 53 31 05 d8 45 86 0d 90 9f 84") # ues ENS1..E.....
hx += bytes.fromhex("07 00 00 00 05 0a 24 84 00 00 19 4c 31 20 4d 65") # ......$....L1 Me
hx += bytes.fromhex("61 73 75 72 65 6d 65 6e 74 56 61 6c 75 65 73 20") # asurementValues
hx += bytes.fromhex("45 4e 53 32 05 d8 4b 86 0d 8f 20 84 07 89 37 77") # ENS2..K... ...7w
hx += bytes.fromhex("05 ee 97 83 cc bf b1 03 02 01 00 14 01 7b 6e 50") # .............{nP
# 02 01 00 68 7b 01 e2 41 00 00 59 51 00 00 19 4c 31 20 4d 65 61 73 75 72 65 6d 65 6e 74 56 61 6c 75 65 73 20 45 4e 53 31 05 d8 45 86 0d 90 9f 84 07 00 00 00 05 0a 24 84 00 00 19 4c 31 20 4d 65 61 73 75 72 65 6d 65 6e 74 56 61 6c 75 65 73 20 45 4e 53 32 05 d8 4b 86 0d 8f 20 84 07 89 37 77 05 ee 97 83 cc bf b1 03
# dgram: to: 123  from: 1  len: 104  crc1: e2  crc2: bfb1
# payload: 41 00 00 59 51 00 00 19 4c 31 20 4d 65 61 73 75 72 65 6d 65 6e 74 56 61 6c 75 65 73 20 45 4e 53 31 05 d8 45 86 0d 90 9f 84 07 00 00 00 05 0a 24 84 00 00 19 4c 31 20 4d 65 61 73 75 72 65 6d 65 6e 74 56 61 6c 75 65 73 20 45 4e 53 32 05 d8 4b 86 0d 8f 20 84 07 89 37 77 05 ee 97 83 cc    A..YQ...L1 MeasurementValues ENS1..E...........$....L1 MeasurementValues ENS2..K... ...7w.....
# ReponseA for 0x51 from 123 len=89
# b'L1 MeasurementValues ENS1' 236.13 V 50.08 Hz 0.00 A 33.27 V
# b'L1 MeasurementValues ENS2' 236.15 V 49.89 Hz 0.01 A 30.91 V

hx += bytes.fromhex("03 00 05 0d 00 ff 03 e8 4c 5a 00 03 02 01 00 0c") # ........LZ......
# 02 01 00 14 01 7b 6e 50 03 00 05 0d 00 ff 03 e8 4c 5a 00 03
# dgram: to: 1  from: 123  len: 20  crc1: 6e  crc2: 5a00
# payload: 50 03 00 05 0d 00 ff 03 e8 4c    P........L

hx += bytes.fromhex("7b 01 eb 51 00 eb c2 03 02 01 00 10 01 7b b5 40") # {..Q.........{.@
# 02 01 00 0c 7b 01 eb 51 00 eb c2 03
# dgram: to: 123  from: 1  len: 12  crc1: eb  crc2: ebc2
# payload: 51 00    Q.

hx += bytes.fromhex("03 00 01 52 a7 21 a4 03 02 01 00 0c 7b 01 eb 41") # ...R.!......{..A
# 02 01 00 10 01 7b b5 40 03 00 01 52 a7 21 a4 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: 21a4
# payload: 40 03 00 01 52 a7    @...R.
# RequestA for 0x52 from 1

hx += bytes.fromhex("01 6d 06 03 02 01 00 10 01 7b b5 40 03 00 01 52") # .m.......{.@...R
# 02 01 00 0c 7b 01 eb 41 01 6d 06 03
# dgram: to: 123  from: 1  len: 12  crc1: eb  crc2: 6d06
# payload: 41 01    A.

hx += bytes.fromhex("a7 21 a4 03 02 01 00 0c 7b 01 eb 41 01 6d 06 03") # .!......{..A.m..
# 02 01 00 10 01 7b b5 40 03 00 01 52 a7 21 a4 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: 21a4
# payload: 40 03 00 01 52 a7    @...R.
# RequestA for 0x52 from 1

# 02 01 00 0c 7b 01 eb 41 01 6d 06 03
# dgram: to: 123  from: 1  len: 12  crc1: eb  crc2: 6d06
# payload: 41 01    A.

hx += bytes.fromhex("02 01 00 10 01 7b b5 40 03 00 01 53 a8 4b ae 03") # .....{.@...S.K..
# 02 01 00 10 01 7b b5 40 03 00 01 53 a8 4b ae 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: 4bae
# payload: 40 03 00 01 53 a8    @...S.
# RequestA for 0x53 from 1

hx += bytes.fromhex("02 01 00 0c 7b 01 eb 41 01 6d 06 03 02 01 00 10") # ....{..A.m......
# 02 01 00 0c 7b 01 eb 41 01 6d 06 03
# dgram: to: 123  from: 1  len: 12  crc1: eb  crc2: 6d06
# payload: 41 01    A.

hx += bytes.fromhex("01 7b b5 40 03 00 01 53 a8 4b ae 03 02 01 00 0c") # .{.@...S.K......
# 02 01 00 10 01 7b b5 40 03 00 01 53 a8 4b ae 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: 4bae
# payload: 40 03 00 01 53 a8    @...S.
# RequestA for 0x53 from 1

hx += bytes.fromhex("7b 01 eb 41 01 6d 06 03 02 01 00 10 01 7b b5 40") # {..A.m.......{.@
# 02 01 00 0c 7b 01 eb 41 01 6d 06 03
# dgram: to: 123  from: 1  len: 12  crc1: eb  crc2: 6d06
# payload: 41 01    A.

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

hx += bytes.fromhex("01 7b b5 64 03 00 01 f1 46 cc 79 03 02 01 00 14") # .{.d....F.y.....
# 02 01 00 10 01 7b b5 64 03 00 01 f1 46 cc 79 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: cc79
# payload: 64 03 00 01 f1 46    d....F
# RequestB for 0xf1 from 1

hx += bytes.fromhex("7b 01 43 65 00 00 05 f1 ef 56 24 4c fb 95 d1 03") # {.Ce.....V$L....
# 02 01 00 14 7b 01 43 65 00 00 05 f1 ef 56 24 4c fb 95 d1 03
# dgram: to: 123  from: 1  len: 20  crc1: 43  crc2: 95d1
# payload: 65 00 00 05 f1 ef 56 24 4c fb    e.....V$L.
# ReponseB for 0xf1 from 123
# ( ef 56 24 4c fb )
# 0.00 0xef

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

hx += bytes.fromhex("00 01 08 5d 02 a9 03 02 01 00 14 7b 01 43 65 00") # ...].......{.Ce.
# 02 01 00 10 01 7b b5 64 03 00 01 08 5d 02 a9 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: 02a9
# payload: 64 03 00 01 08 5d    d....]
# RequestB for 0x08 from 1

hx += bytes.fromhex("00 05 08 05 0a 70 3e 1a 88 82 03") # .....p>....
# 02 01 00 14 7b 01 43 65 00 00 05 08 05 0a 70 3e 1a 88 82 03
# dgram: to: 123  from: 1  len: 20  crc1: 43  crc2: 8882
# payload: 65 00 00 05 08 05 0a 70 3e 1a    e......p>.
# ReponseB for 0x08 from 123
# ( 05 0a 70 3e 1a )
# 0.00 V

##
## Data recorded while doing device recovery in the StecaGrid Software
##

hx += bytes.fromhex("02 01 00 0c 01 7b c6 20 03 79 8c 03 02 01 02 a8") # .....{. .y......
# 02 01 00 0c 01 7b c6 20 03 79 8c 03
# dgram: to: 1  from: 123  len: 12  crc1: c6  crc2: 798c
# payload: 20 03     .

hx += bytes.fromhex("7b 01 77 21 00 02 99 53 74 65 63 61 47 72 69 64") # {.w!...StecaGrid
hx += bytes.fromhex("20 33 36 30 30 00 37 34 38 36 31 33 30 30 35 32") #  3600.7486130052
hx += bytes.fromhex("31 32 38 35 30 30 32 39 00 00 11 48 4d 49 20 42") # 12850029...HMI B
hx += bytes.fromhex("46 41 50 49 20 00 02 05 00 00 00 00 31 39 2e 30") # FAPI .......19.0
hx += bytes.fromhex("33 2e 32 30 31 33 20 31 34 3a 33 38 3a 35 39 00") # 3.2013 14:38:59.
hx += bytes.fromhex("48 4d 49 20 46 42 4c 20 00 01 02 00 03 00 00 30") # HMI FBL .......0
hx += bytes.fromhex("35 2e 30 34 2e 32 30 31 33 20 31 31 3a 34 36 3a") # 5.04.2013 11:46:
hx += bytes.fromhex("32 30 00 48 4d 49 20 41 50 50 20 00 01 0f 00 00") # 20.HMI APP .....
hx += bytes.fromhex("00 00 32 36 2e 30 37 2e 32 30 31 33 20 31 33 3a") # ..26.07.2013 13:
hx += bytes.fromhex("31 39 3a 30 36 00 48 4d 49 20 50 41 52 20 00 02") # 19:06.HMI PAR ..
hx += bytes.fromhex("00 00 01 00 00 32 36 2e 30 37 2e 32 30 31 33 20") # .....26.07.2013
hx += bytes.fromhex("31 33 3a 31 39 3a 30 36 00 48 4d 49 20 4f 45 4d") # 13:19:06.HMI OEM
hx += bytes.fromhex("20 00 01 00 00 01 00 00 31 31 2e 30 36 2e 32 30") #  .......11.06.20
hx += bytes.fromhex("31 33 20 30 38 3a 31 31 3a 32 39 00 50 55 20 42") # 13 08:11:29.PU B
hx += bytes.fromhex("46 41 50 49 20 00 02 05 00 00 00 00 31 39 2e 30") # FAPI .......19.0
hx += bytes.fromhex("33 2e 32 30 31 33 5f 31 34 3a 33 38 3a 34 32 00") # 3.2013_14:38:42.
hx += bytes.fromhex("50 55 20 46 42 4c 20 00 01 01 00 01 00 00 31 39") # PU FBL .......19
hx += bytes.fromhex("2e 31 32 2e 32 30 31 32 5f 31 36 3a 33 36 3a 30") # .12.2012_16:36:0
hx += bytes.fromhex("34 00 50 55 20 41 50 50 20 00 05 04 00 00 00 00") # 4.PU APP .......
hx += bytes.fromhex("30 33 2e 30 35 2e 32 30 31 33 5f 30 39 3a 33 37") # 03.05.2013_09:37
hx += bytes.fromhex("3a 35 35 00 50 55 20 50 41 52 20 00 05 03 00 00") # :55.PU PAR .....
hx += bytes.fromhex("00 00 33 31 2e 30 31 2e 32 30 31 33 5f 31 33 3a") # ..31.01.2013_13:
hx += bytes.fromhex("34 37 3a 32 34 00 45 4e 53 31 20 42 46 41 50 49") # 47:24.ENS1 BFAPI
hx += bytes.fromhex("20 00 02 05 00 00 00 00 31 39 2e 30 33 2e 32 30") #  .......19.03.20
hx += bytes.fromhex("31 33 5f 31 34 3a 33 38 3a 35 31 00 45 4e 53 31") # 13_14:38:51.ENS1
hx += bytes.fromhex("20 46 42 4c 20 00 01 01 00 01 00 00 31 39 2e 31") #  FBL .......19.1
hx += bytes.fromhex("32 2e 32 30 31 32 5f 31 36 3a 33 34 3a 34 37 00") # 2.2012_16:34:47.
hx += bytes.fromhex("45 4e 53 31 20 41 50 50 20 00 03 27 00 00 00 00") # ENS1 APP ..'....
hx += bytes.fromhex("31 31 2e 30 37 2e 32 30 31 33 5f 31 34 3a 33 39") # 11.07.2013_14:39
hx += bytes.fromhex("3a 35 30 00 45 4e 53 31 20 50 41 52 20 00 13 00") # :50.ENS1 PAR ...
hx += bytes.fromhex("00 0e 00 00 31 31 2e 30 37 2e 32 30 31 33 5f 31") # ....11.07.2013_1
hx += bytes.fromhex("34 3a 34 30 3a 30 33 00 45 4e 53 32 20 42 46 41") # 4:40:03.ENS2 BFA
hx += bytes.fromhex("50 49 20 00 02 05 00 00 00 00 31 39 2e 30 33 2e") # PI .......19.03.
hx += bytes.fromhex("32 30 31 33 5f 31 34 3a 33 38 3a 35 31 00 45 4e") # 2013_14:38:51.EN
hx += bytes.fromhex("53 32 20 46 42 4c 20 00 01 01 00 01 00 00 31 39") # S2 FBL .......19
hx += bytes.fromhex("2e 31 32 2e 32 30 31 32 5f 31 36 3a 33 34 3a 34") # .12.2012_16:34:4
hx += bytes.fromhex("37 00 45 4e 53 32 20 41 50 50 20 00 03 27 00 00") # 7.ENS2 APP ..'..
hx += bytes.fromhex("00 00 31 31 2e 30 37 2e 32 30 31 33 5f 31 34 3a") # ..11.07.2013_14:
hx += bytes.fromhex("33 39 3a 35 30 00 45 4e 53 32 20 50 41 52 20 00") # 39:50.ENS2 PAR .
hx += bytes.fromhex("13 00 00 0e 00 00 31 31 2e 30 37 2e 32 30 31 33") # ......11.07.2013
hx += bytes.fromhex("5f 31 34 3a 34 30 3a 30 33 00 03 48 4d 49 00 01") # _14:40:03..HMI..
hx += bytes.fromhex("50 55 00 03 45 4e 53 32 00 02 4e 65 74 31 31 00") # PU..ENS2..Net11.
hx += bytes.fromhex("30 46 79 03 02 01 00 10 01 7b b5 64 03 00 01 09") # 0Fy......{.d....
# 02 01 02 a8 7b 01 77 21 00 02 99 53 74 65 63 61 47 72 69 64 20 33 36 30 30 00 37 34 38 36 31 33 30 30 35 32 31 32 38 35 30 30 32 39 00 00 11 48 4d 49 20 42 46 41 50 49 20 00 02 05 00 00 00 00 31 39 2e 30 33 2e 32 30 31 33 20 31 34 3a 33 38 3a 35 39 00 48 4d 49 20 46 42 4c 20 00 01 02 00 03 00 00 30 35 2e 30 34 2e 32 30 31 33 20 31 31 3a 34 36 3a 32 30 00 48 4d 49 20 41 50 50 20 00 01 0f 00 00 00 00 32 36 2e 30 37 2e 32 30 31 33 20 31 33 3a 31 39 3a 30 36 00 48 4d 49 20 50 41 52 20 00 02 00 00 01 00 00 32 36 2e 30 37 2e 32 30 31 33 20 31 33 3a 31 39 3a 30 36 00 48 4d 49 20 4f 45 4d 20 00 01 00 00 01 00 00 31 31 2e 30 36 2e 32 30 31 33 20 30 38 3a 31 31 3a 32 39 00 50 55 20 42 46 41 50 49 20 00 02 05 00 00 00 00 31 39 2e 30 33 2e 32 30 31 33 5f 31 34 3a 33 38 3a 34 32 00 50 55 20 46 42 4c 20 00 01 01 00 01 00 00 31 39 2e 31 32 2e 32 30 31 32 5f 31 36 3a 33 36 3a 30 34 00 50 55 20 41 50 50 20 00 05 04 00 00 00 00 30 33 2e 30 35 2e 32 30 31 33 5f 30 39 3a 33 37 3a 35 35 00 50 55 20 50 41 52 20 00 05 03 00 00 00 00 33 31 2e 30 31 2e 32 30 31 33 5f 31 33 3a 34 37 3a 32 34 00 45 4e 53 31 20 42 46 41 50 49 20 00 02 05 00 00 00 00 31 39 2e 30 33 2e 32 30 31 33 5f 31 34 3a 33 38 3a 35 31 00 45 4e 53 31 20 46 42 4c 20 00 01 01 00 01 00 00 31 39 2e 31 32 2e 32 30 31 32 5f 31 36 3a 33 34 3a 34 37 00 45 4e 53 31 20 41 50 50 20 00 03 27 00 00 00 00 31 31 2e 30 37 2e 32 30 31 33 5f 31 34 3a 33 39 3a 35 30 00 45 4e 53 31 20 50 41 52 20 00 13 00 00 0e 00 00 31 31 2e 30 37 2e 32 30 31 33 5f 31 34 3a 34 30 3a 30 33 00 45 4e 53 32 20 42 46 41 50 49 20 00 02 05 00 00 00 00 31 39 2e 30 33 2e 32 30 31 33 5f 31 34 3a 33 38 3a 35 31 00 45 4e 53 32 20 46 42 4c 20 00 01 01 00 01 00 00 31 39 2e 31 32 2e 32 30 31 32 5f 31 36 3a 33 34 3a 34 37 00 45 4e 53 32 20 41 50 50 20 00 03 27 00 00 00 00 31 31 2e 30 37 2e 32 30 31 33 5f 31 34 3a 33 39 3a 35 30 00 45 4e 53 32 20 50 41 52 20 00 13 00 00 0e 00 00 31 31 2e 30 37 2e 32 30 31 33 5f 31 34 3a 34 30 3a 30 33 00 03 48 4d 49 00 01 50 55 00 03 45 4e 53 32 00 02 4e 65 74 31 31 00 30 46 79 03
# dgram: to: 123  from: 1  len: 680  crc1: 77  crc2: 4679
# payload: 21 00 02 99 53 74 65 63 61 47 72 69 64 20 33 36 30 30 00 37 34 38 36 31 33 30 30 35 32 31 32 38 35 30 30 32 39 00 00 11 48 4d 49 20 42 46 41 50 49 20 00 02 05 00 00 00 00 31 39 2e 30 33 2e 32 30 31 33 20 31 34 3a 33 38 3a 35 39 00 48 4d 49 20 46 42 4c 20 00 01 02 00 03 00 00 30 35 2e 30 34 2e 32 30 31 33 20 31 31 3a 34 36 3a 32 30 00 48 4d 49 20 41 50 50 20 00 01 0f 00 00 00 00 32 36 2e 30 37 2e 32 30 31 33 20 31 33 3a 31 39 3a 30 36 00 48 4d 49 20 50 41 52 20 00 02 00 00 01 00 00 32 36 2e 30 37 2e 32 30 31 33 20 31 33 3a 31 39 3a 30 36 00 48 4d 49 20 4f 45 4d 20 00 01 00 00 01 00 00 31 31 2e 30 36 2e 32 30 31 33 20 30 38 3a 31 31 3a 32 39 00 50 55 20 42 46 41 50 49 20 00 02 05 00 00 00 00 31 39 2e 30 33 2e 32 30 31 33 5f 31 34 3a 33 38 3a 34 32 00 50 55 20 46 42 4c 20 00 01 01 00 01 00 00 31 39 2e 31 32 2e 32 30 31 32 5f 31 36 3a 33 36 3a 30 34 00 50 55 20 41 50 50 20 00 05 04 00 00 00 00 30 33 2e 30 35 2e 32 30 31 33 5f 30 39 3a 33 37 3a 35 35 00 50 55 20 50 41 52 20 00 05 03 00 00 00 00 33 31 2e 30 31 2e 32 30 31 33 5f 31 33 3a 34 37 3a 32 34 00 45 4e 53 31 20 42 46 41 50 49 20 00 02 05 00 00 00 00 31 39 2e 30 33 2e 32 30 31 33 5f 31 34 3a 33 38 3a 35 31 00 45 4e 53 31 20 46 42 4c 20 00 01 01 00 01 00 00 31 39 2e 31 32 2e 32 30 31 32 5f 31 36 3a 33 34 3a 34 37 00 45 4e 53 31 20 41 50 50 20 00 03 27 00 00 00 00 31 31 2e 30 37 2e 32 30 31 33 5f 31 34 3a 33 39 3a 35 30 00 45 4e 53 31 20 50 41 52 20 00 13 00 00 0e 00 00 31 31 2e 30 37 2e 32 30 31 33 5f 31 34 3a 34 30 3a 30 33 00 45 4e 53 32 20 42 46 41 50 49 20 00 02 05 00 00 00 00 31 39 2e 30 33 2e 32 30 31 33 5f 31 34 3a 33 38 3a 35 31 00 45 4e 53 32 20 46 42 4c 20 00 01 01 00 01 00 00 31 39 2e 31 32 2e 32 30 31 32 5f 31 36 3a 33 34 3a 34 37 00 45 4e 53 32 20 41 50 50 20 00 03 27 00 00 00 00 31 31 2e 30 37 2e 32 30 31 33 5f 31 34 3a 33 39 3a 35 30 00 45 4e 53 32 20 50 41 52 20 00 13 00 00 0e 00 00 31 31 2e 30 37 2e 32 30 31 33 5f 31 34 3a 34 30 3a 30 33 00 03 48 4d 49 00 01 50 55 00 03 45 4e 53 32 00 02 4e 65 74 31 31 00 30    !...StecaGrid 3600.748613005212850029...HMI BFAPI .......19.03.2013 14:38:59.HMI FBL .......05.04.2013 11:46:20.HMI APP .......26.07.2013 13:19:06.HMI PAR .......26.07.2013 13:19:06.HMI OEM .......11.06.2013 08:11:29.PU BFAPI .......19.03.2013_14:38:42.PU FBL .......19.12.2012_16:36:04.PU APP .......03.05.2013_09:37:55.PU PAR .......31.01.2013_13:47:24.ENS1 BFAPI .......19.03.2013_14:38:51.ENS1 FBL .......19.12.2012_16:34:47.ENS1 APP ..'....11.07.2013_14:39:50.ENS1 PAR .......11.07.2013_14:40:03.ENS2 BFAPI .......19.03.2013_14:38:51.ENS2 FBL .......19.12.2012_16:34:47.ENS2 APP ..'....11.07.2013_14:39:50.ENS2 PAR .......11.07.2013_14:40:03..HMI..PU..ENS2..Net11.0
# ReponseC for 83 from 123 len= 665

hx += bytes.fromhex("5e 85 6e 03 02 01 00 24 7b 01 2a 65 00 00 15 09") # ^.n....${.*e....
# 02 01 00 10 01 7b b5 64 03 00 01 09 5e 85 6e 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: 856e
# payload: 64 03 00 01 09 5e    d....^
# RequestB for 0x09 from 1

hx += bytes.fromhex("37 34 38 36 31 33 59 49 30 30 35 32 31 32 38 35") # 748613YI00521285
hx += bytes.fromhex("30 30 32 39 9f ab 3b 03 02 01 00 10 01 7b b5 54") # 0029..;......{.T
# 02 01 00 24 7b 01 2a 65 00 00 15 09 37 34 38 36 31 33 59 49 30 30 35 32 31 32 38 35 30 30 32 39 9f ab 3b 03
# dgram: to: 123  from: 1  len: 36  crc1: 2a  crc2: ab3b
# payload: 65 00 00 15 09 37 34 38 36 31 33 59 49 30 30 35 32 31 32 38 35 30 30 32 39 9f    e....748613YI005212850029.
# ReponseB for 0x09 from 123

hx += bytes.fromhex("03 00 01 32 87 e1 78 03") # ...2..x.
# 02 01 00 10 01 7b b5 54 03 00 01 32 87 e1 78 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: e178
# payload: 54 03 00 01 32 87    T...2.

hx += bytes.fromhex("02 01 00 0c 7b 01 eb 55 11 bf 92 03") # ....{..U....
# 02 01 00 0c 7b 01 eb 55 11 bf 92 03
# dgram: to: 123  from: 1  len: 12  crc1: eb  crc2: bf92
# payload: 55 11    U.

hx += bytes.fromhex("02 01 00 14 7b 01 43 55 00 00 05 32 0f 13 24 01") # ....{.CU...2..$.
hx += bytes.fromhex("ce b5 cb 03 02 01 00 10 01 7b b5 40 03 00 01 1d") # .........{.@....
# 02 01 00 14 7b 01 43 55 00 00 05 32 0f 13 24 01 ce b5 cb 03
# dgram: to: 123  from: 1  len: 20  crc1: 43  crc2: b5cb
# payload: 55 00 00 05 32 0f 13 24 01 ce    U...2..$..

hx += bytes.fromhex("72 30 95 03 02 01 00 25 7b 01 ce 41 00 00 16 1d") # r0.....%{..A....
# 02 01 00 10 01 7b b5 40 03 00 01 1d 72 30 95 03
# dgram: to: 1  from: 123  len: 16  crc1: b5  crc2: 3095
# payload: 40 03 00 01 1d 72    @....r
# RequestA for 0x1d (Nominal Power) from 1

hx += bytes.fromhex("00 00 0e 4e 6f 6d 69 6e 61 6c 20 50 6f 77 65 72") # ...Nominal Power
hx += bytes.fromhex("3a 0b c2 00 8a 0c f4 46 03 02 01 00 0c 02 7b c0") # :......F......{.
# 02 01 00 25 7b 01 ce 41 00 00 16 1d 00 00 0e 4e 6f 6d 69 6e 61 6c 20 50 6f 77 65 72 3a 0b c2 00 8a 0c f4 46 03
# dgram: to: 123  from: 1  len: 37  crc1: ce  crc2: f446
# payload: 41 00 00 16 1d 00 00 0e 4e 6f 6d 69 6e 61 6c 20 50 6f 77 65 72 3a 0b c2 00 8a 0c    A.......Nominal Power:.....
# ReponseA for 0x1d from 123 len=22
# b'Nominal Power:' 3600.00 W

hx += bytes.fromhex("20 03 33 5a 03") #  .3Z.
# 02 01 00 0c 02 7b c0 20 03 33 5a 03
# dgram: to: 2  from: 123  len: 12  crc1: c0  crc2: 335a
# payload: 20 03     .

hx += bytes.fromhex("02 01 00 0c 02 7b c0 20 03 33 5a 03") # .....{. .3Z.
# 02 01 00 0c 02 7b c0 20 03 33 5a 03
# dgram: to: 2  from: 123  len: 12  crc1: c0  crc2: 335a
# payload: 20 03     .


hx += bytes.fromhex("02 01 00 14 01 7b 6e 50 03 00 05 0d 00 ff 03 e8") # .....{nP........
hx += bytes.fromhex("4c 5a 00 03 02 01 00 0c 7b 01 eb 51 00 eb c2 03") # LZ......{..Q....
# 02 01 00 14 01 7b 6e 50 03 00 05 0d 00 ff 03 e8 4c 5a 00 03
# dgram: to: 1  from: 123  len: 20  crc1: 6e  crc2: 5a00
# payload: 50 03 00 05 0d 00 ff 03 e8 4c    P........L

# 02 01 00 0c 7b 01 eb 51 00 eb c2 03
# dgram: to: 123  from: 1  len: 12  crc1: eb  crc2: ebc2
# payload: 51 00    Q.


if False: # set to True to process included recorded data
    xprocess_telegram(hx)
    rest = process_telegrams(hx)
    print ("rest:",rest)
else:
    while True:
        try:
            data = ser.read(16)
            if data:
                xprocess_telegram(data)
                buffer = buffer + data
                buffer = process_telegrams(buffer)

        except KeyboardInterrupt:
            break

# Close the serial port
ser.close()
