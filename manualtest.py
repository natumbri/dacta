from SerialEmulator import SerialEmulator
emulator = SerialEmulator('./ttydevice','./ttyclient') 
import serial

ser = serial.Serial('./ttyclient')
buff = b'x' + ser.read(17)
print(len(buff))

while len(buff) < 19: # only happens if above read times out
    # print("Warning: missed a packet.")
    buff = buff + ser.read(1)
    print(len(buff))
print(buff)

emulator.stop()