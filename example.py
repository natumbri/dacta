from dacta import Dacta
import time
import os
import code

print 'Hit ^C at any point for interactive control. Dacta object\'s name is "d".'

d = Dacta('COMxx or /dev/ttyX') # put your serial port name here

try:
    while True:
        for port in range(8):
            d.sendPortCmd(d.CMD_PORTREV, port)
            d.sendPortCmd(d.CMD_PORTONX, port)
            (v, s, r) = d.getSensors()
            print v, s, r
            time.sleep(1)
except KeyboardInterrupt:
    print
    print
    print "Dacta object's name is d. Please remember to d.close() before"
    print "you quit(), or else you'll be stuck waiting forever."
    print
    print
    code.interact(local=locals())
