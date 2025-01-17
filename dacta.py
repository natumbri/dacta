""" Allow interaction with Lego 9751 / 70909 command module. """
__author__ = 'Steven Shamlian'
__version__ = '2014-04-03'
__license__ = ('This software is released under rev. 42 of the Beer-Ware '
               'license. Lego@shamlian.net wrote this software. As long as '
               'you retain this notice, you can do whatever you want with it. '
               'If we meet some day, and you think it\'s worth it, you can '
               'buy me a beer in return. --Steve')

import serial, threading, queue, time

class Dacta:
    _ser = None # serial object for raw comms
    _outQueue = queue.Queue() # queue for outgoing comms
    _threadList = [] # list of active threads -- in, out, and keepalive
    _running = threading.Event() # used to safely shut things down on close()

    _NUM_SENSORS = 8
    
    _sensorValues = [0] * _NUM_SENSORS
    _sensorStatus = [0] * _NUM_SENSORS
    _rotations = [0] * _NUM_SENSORS
    _sensorLock = threading.Lock() # mutex for sensor values

    # initialization strings
    _INIT_ON = b'p\0'
    _INIT_START = b'###Do you byte, when I knock?$$$'
    _INIT_RETURN = b'###Just a bit off the block!$$$'

    # commands from http://www.blockcad.net/dacta/
    CMD_NOP = '\x02'        # 0000 0010

                            # xxxx xppp where x the command and p is port number (0-7)
    CMD_PORTONL = '\x10'    # 0001 0000
    CMD_PORTONR = '\x18'    # 0001 1000
    CMD_PORTREV = '\x20'    # 0010 0000
    CMD_PORTONX = '\x28'    # 0010 1000
    CMD_PORTOFF = '\x30'    # 0011 0000  # check to see if low nibble does anything
    CMD_PORTDRL = '\x40'    # 0100 0000
    CMD_PORTDRR = '\x48'    # 0100 1000
    CMD_KILLALL = '\x70'    # 0111 0000  # completely disconnects interface

                            # xxxx xsss oooooooo where x the command, s is power setting and o is the output port (one bit for each)
    _PARAM_POWER = '\xb0'   # 1011 0000 00000000

    PORT_A = 0
    PORT_B = 1
    PORT_C = 2
    PORT_D = 3
    PORT_E = 4
    PORT_F = 5
    PORT_G = 6
    PORT_H = 7
    PORT_1 = 0
    PORT_2 = 1
    PORT_3 = 2
    PORT_4 = 3
    PORT_5 = 4
    PORT_6 = 5
    PORT_7 = 6
    PORT_8 = 7
        

    def taskKeepAlive(self):
        """ Internal task for sending a nop every 2 seconds (or so). """
        while self._running.is_set():
            time.sleep(1.9)
            self._outQueue.put(self.CMD_NOP)

    def taskWrite(self):
        """ Internal task to write commands to the serial port if available. """
        while self._running.is_set():
            item = self._outQueue.get(block=True).encode()
            if self._ser == None:
                print(repr(item))
            else:
                self._ser.write(item)

    def sendPortCmd(self, cmd, port):
        """ Function for sending raw one-byte commands to a port.
        Ports should be 0-indexed; alternatively, use PORT_[letter].
        Notable commands are as follows:

        CMD_PORTDRL: Set port direction to "left."
        CMD_PORTDRR: Set port direction to "right."
        CMD_PORTOFF: Shut port off.
        CMD_PORTONL: Turn on port, going "left."
        CMD_PORTONR: Turn on port, going "right."
        CMD_PORTONX: Turn on port in the same direction it was last.
        CMD_PORTREV: Reverse port output direction.
        CMD_KILLALL: Completely disconnects 9751/70909. Use close() instead.
        """
        
        port = port & 7
        self._outQueue.put(chr(ord(cmd) | port))

    def setPower(self, port, power):
        """ Given 0-indexed port number and power level between 0 and 7,
        inclusive, set port's power appropriately. """
        
        self.sendPortCmd(self._PARAM_POWER, power)
        port = port & 7
        self._outQueue.put(chr(1 << port))

    def taskRead(self):
        """ Internal state machine to read data from the 70909 / 9751. """
        if self._ser == None:
            print("Note: no inputs are available.")
            return

        buff = self._ser.read(19)

        while self._running.is_set():
            if buff[0] == 0 and len(buff) == 19:
                checksum = 0
                for c in buff:
                    checksum += c
                if (checksum & 0xff) == 0xff:
                    # print("Got a packet!") # debug
                    # print(repr(buff)) # debug
                    
                    self._sensorLock.acquire()
                    (self._sensorValues[0], self._sensorStatus[0], change) = self._decodeInput(buff[14],buff[15]);
                    (self._sensorValues[1], self._sensorStatus[1], change) = self._decodeInput(buff[10],buff[11]);
                    (self._sensorValues[2], self._sensorStatus[2], change) = self._decodeInput(buff[6],buff[7]);
                    (self._sensorValues[3], self._sensorStatus[3], change) = self._decodeInput(buff[2],buff[3]);
                    
                    (self._sensorValues[4], self._sensorStatus[4], change) = self._decodeInput(buff[16],buff[17]);
                    self._rotations[4] += change
                    (self._sensorValues[5], self._sensorStatus[5], change) = self._decodeInput(buff[12],buff[13]);
                    self._rotations[5] += change
                    (self._sensorValues[6], self._sensorStatus[6], change) = self._decodeInput(buff[8],buff[9]);
                    self._rotations[6] += change
                    (self._sensorValues[7], self._sensorStatus[7], change) = self._decodeInput(buff[4],buff[5]);
                    self._rotations[7] += change
                    self._sensorLock.release()
                    
                    # getting ready to go around again;
                    buff = b'x' + self._ser.read(18)  # the 'x' drops off at the buff[1:] at the end of the while loop
                    while len(buff) < 19 and self._running.is_set(): # only happens if above read times out, which can happen on shutdown
                        print("Warning: missed a byte.")
                        buff = buff + self._ser.read(1)

            buff = buff[1:] + self._ser.read(1)  # shift buffer left and read one byte

    def _decodeInput(self, b1, b2):
        """
        Internal function to unpack bitfields from 70909 / 9751 

        << is bitshift operator: n << m = shift n left by m bits
        | is bitwise OR operator: n | m = bitwise OR of n and m
        >> is bitshift operator: n >> m = shift n right by m bits
        & is bitwise AND operator: n & m = bitwise AND of n and m

        input value is 2 bytes (b1, b2), with the following format:
        aaaaaaaa aaxxxxxxxx          

        a = analog value (10 bits)  (0-1023) 
        x = status value (6 bits)   
      
        """

        # # 1 - shift b1 left by 2 bits (by pushing in two 0s on the right), to make it a 10 bit number
        # # (aaaaaaa -> aaaaaaaa00)
        # # 2 - shift b2 right by 6 bits by pushing copies of the leftmost bit in from the left 
        # # and let the rightmost bits fall off, then bitwise AND with 0x03 (0000 0011),
        # # setting all the bits from b2 other than the rightmost two bits to 0 (aaxxxxxxxx -> 000000aa)
        # # 3 -  bitwise OR of b1 and what is left of b2 (the original 2 leftmost bits) (aaaaaaaa00 | 000000aa = aaaaaaaaaa)
        # value = (ord(b1) << 2) | ((ord(b2) >> 6) & 0x03)
        value = (b1 << 2) | ((b2 >> 6) & 0x03)
        
        # # 0x3F = 63 = 0011 1111 - assigns to 'state' the value of b2 bitwise ANDed with constant 0x3F. 
        # # This has the effect of setting the leftmost two bits in b2 to 0 and preserving the 
        # # rightmost 6 bits (status value) from b2
        # state = ord(b2) & 0x3F
        state = b2 & 0x3F  

        # # 3 = 0000 0011 - assigns to 'change' the value of state bitwise ANDed with constant 3. 
        # # This has the effect of setting all the bits in state other than the rightmost two bits to 0
        # # and preserving the rightmost bits from state. 
        change = state & 3
        
        if state & 4 == 0:
            change *= -1
        
        return (value, state, change)

    def getSensors(self):
        """ Returns tuple of raw value, status, and rotation counters. """
        self._sensorLock.acquire()
        valu = list(self._sensorValues)
        stat = list(self._sensorStatus)
        rot = list(self._rotations)
        self._sensorLock.release()
        return (valu, stat, rot)

    def getValue(self, port):
        """ Given 0-indexed port number, returns raw sensor value. """
        (v, s, r) = self.getSensors()
        return v[port & 7]

    def getStatus(self, port):
        """ Given 0-indexed port number, returns raw status value. """
        (v, s, r) = self.getSensors()
        return s[port & 7]

    def getRotation(self, port):
        """ Given 0-indexed port number, returns value of internal counter
        for angular rotation. Note that there are 16 counts per revolution.
        """
        (v, s, r) = self.getSensors()
        return r[port & 7]

    def clearRotation(self, port):
        """ Given 0-indexed port number, clears internal counter for angular
        rotation. Note that there are 16 counts per revolution.
        """
        self._sensorLock.acquire()
        self._rotations[port & 7] = 0
        self._sensorLock.release()

    def isPressed(self, port):
        """ Given 0-indexed port number, returns whether button is pressed.
        """
        if self.getValue(port) < 1000:
            return True
        return False

    def getTempF(self, port):
        """ Given 0-indexed port number, returns temperature in deg. Fahrenheit.
        """
        return (760.0 - self.getValue(port)) / 4.4 + 32.0

    def getTempC(self, port):
        """ Given 0-indexed port number, returns temperature in deg. Celsius.
        """
        return ((760.0 - self.getValue(port)) / 4.4) * 5.0 / 9.0

    def close(self):
        """ Safely terminates helper threads and closes serial port. """
        
        print("Shutting down.")
        self._outQueue.put(self.CMD_KILLALL)
        time.sleep(0.5)
        self._running.clear()
        for thread in self._threadList:
            while thread.is_alive():
                time.sleep(0.1)
        if self._ser != None:
            self._ser.close()
    
    def __init__(self, comPort):
        """ Initialize communications to 9751/70909 and launch helper threads.
        comPort -- COM port number or name (like 'COM1' or '/dev/ttyUSB0')
        """
        
        try:
            self._ser = serial.Serial(comPort, 9600, timeout = 2)
        except serial.SerialException:
            print("Could not open port " + repr(comPort) + "; using stdout instead.")
            self._ser = None

        self._threadList.append(threading.Thread(target = self.taskKeepAlive))
        self._threadList.append(threading.Thread(target = self.taskWrite))
        self._threadList.append(threading.Thread(target = self.taskRead))

        if self._ser != None:
            self._ser.write(self._INIT_ON)
            # should probably do something with return values here, but I'm lazy
            self._ser.write(self._INIT_START)
            confirmation = self._ser.read(len(self._INIT_RETURN))
            while confirmation != self._INIT_RETURN:
                # print(confirmation) # debug
                confirmation = confirmation[1:] + self._ser.read(1)
            print("Got confirmation string.")

        self._running.set()
        for thread in self._threadList:
            thread.start()

    def __del__(self):
        """ Should be called on close, but there's a bug. Call close() instead.
        """
        self.close()
