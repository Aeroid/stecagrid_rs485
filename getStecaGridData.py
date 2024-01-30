import struct
import serial # pip3 install pyserial

DEBUG = False

SERIAL_DEVICE   = "/dev/ttyS0"
SERIAL_BYTES    = serial.EIGHTBITS
SERIAL_PARITY   = serial.PARITY_NONE
SERIAL_SBIT     = serial.STOPBITS_ONE
SERIAL_BAUDRATE = 38400
SERIAL_TIMEOUT  = 1
    
# 16 byte modbus rs845 response to read AC power of steca grid
#  HEX array to request ACpower from StacaGrid:
#  02 01 00 10 01 C9 65 40 03 00 01 29 7E 29 BE 03
#  Example of a StecaGrid answer:
#  02 01 00 1F C9 01 84 41 00 00 10 29 00 00 08 41 43 50 6F 77 65 72 3A 0B A2 78 85 FB 49 4C 03
#  Other Example
#  02 01 00 1e 7b 01 3d 41 00 00 0f 29 00 00 07 41 43 50 6f 77 65 72 00 00 01 2d 44 7b b1 03 02 01 00 10 01 7b b5 40 03 00 01 51 a6 d4 c0 03 
#  ....{.=A...)...ACPower...-D{.......{.@...Q....

SG_AC_POWER_RESPONSE = [
        0x02, #   2 = 
        0x01, #   1 = 
        0x00, #   0 = 
        0x10, #  16 = 
        0x01, #   1 = 
        0xC9, # 201 = 
        0x65, # 101 = 
        0x40, #  64 = 
        0x03, #   3 = 
        0x00, #   0 = 
        0x01, #   1 = 
        0x29, #  41 = 
        0x7E, # 126 = 
        0x29, #  41 = 
        0xBE, # 190 = 
        0x03  #   3 = 
    ]

def getStecaGridACPower():
  msg = SG_AC_POWER_RESPONSE

  with port as s:
    if DEBUG:
        print("serial write " + str(msg))

    s.write(msg)

    in_data = s.read(size=31)
    if DEBUG:
        print("ser read " + str(in_data))
        i = 0
        for d in in_data:
            print(str(i) + " " + str(in_data[i]) + " " + chr(in_data[i]) + " 0x%02x" % in_data[i])
            i = i + 1

    if len(in_data) < 30:
        if DEBUG:
            print("received data is too short: "+str(len(in_data)))
        return 0
    
    ac_bytes = in_data[23:27]
    if len(in_data) == 30:
        ac_bytes = in_data[22:26] 

    if ac_bytes[0] == 0x0B:
        # AC power is > 0
        iacpower = ((ac_bytes[3] << 8 | ac_bytes[1]) << 8 | ac_bytes[2]) << 7 # formula to float - conversion according to Steca

        if DEBUG:
            print("iacpower 0x%0X" % iacpower)
            print("iacpower " + str(iacpower))
            print("in_data[24-27] 0x%02x%02x%02x" % (ac_bytes[1] , ac_bytes[2] , ac_bytes[3]))

        tmp_data = [ 0, int(ac_bytes[1]), int(ac_bytes[2]), int(ac_bytes[3]) ]

        facpower, = struct.unpack('f', struct.pack('I', iacpower))

        if DEBUG:
            print("AC Power:", facpower)

        return facpower
    elif ac_bytes[0] == 0x0C:
        # AC power is 0
        return 0
    else:
        if DEBUG:
            print("received data is incorrect")
        return 0

if __name__ == "__main__":
    port = serial.Serial(baudrate=SERIAL_BAUDRATE, port=SERIAL_DEVICE, timeout=SERIAL_TIMEOUT, parity=SERIAL_PARITY, stopbits=SERIAL_SBIT, bytesize=SERIAL_BYTES, xonxoff=0, rtscts=0)
    if DEBUG:
        print(port.get_settings())
        
    ac_power = getStecaGridACPower()

    print(ac_power)

    port.close()
