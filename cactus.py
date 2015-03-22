###############################################################################
# Cactus Tracker v1.0.6 / January 13, 2015
# by Maksym Ganenko <buratin.barabanus at Google Mail>
###############################################################################

import serial, re
import sys, os, traceback
from datetime import datetime

# arduino serial port in your system
SERIAL  = (sys.platform == "win32") and "COM6" or "/dev/tty.usbmodem1421"

# input / output files
INIFILE = "cactusini.txt"
CMDFILE = "cactuscmd.txt"
LOGFILE = "cactuslog.txt"

# log update period in seconds
UPDATE_PERIOD_SEC = 600

###############################################################################

def execute(cmdfile, **argv):
    if os.path.isfile(cmdfile):
        try: # input
            fcmd = open(cmdfile)
            stream.write(((fcmd.read().strip() + " ") * 10).strip())
            fcmd.close()

            if "renameTo" in argv:
                dstfile = argv["renameTo"]
                if os.path.isfile(dstfile): os.remove(dstfile)
                os.rename(cmdfile, dstfile)
        except: traceback.print_exc()
        if fcmd and not fcmd.closed: fcmd.close()

firstRun = True
fcmd, flog, timemark, lastState = None, None, None, None
stream = serial.Serial(SERIAL, 115200)

while True:
    s = stream.readline()
    if "mode" in s:
        record      = dict(re.findall(r"(\w+)\s+=\s+([-.\d]+|nan)", s))
        mode        = int(record["mode"])
        tempLM35    = float(record["tempLM35"])
        tempDHT22   = float(record["tempDHT22"])
        humidity    = float(record["humidityDHT22"])
        heater      = int(record["heater"])
        heaterFrom  = float(record["heaterFrom"])
        heaterTo    = float(record["heaterTo"])
        light       = int(record["light"])
        state       = (mode, heater, heaterFrom, heaterTo, light)

        if firstRun:
            execute(INIFILE)
            firstRun = False

        execute(CMDFILE, renameTo = INIFILE)

        timeout = not timemark or \
                 (datetime.now() - timemark).seconds > UPDATE_PERIOD_SEC

        if timeout or state != lastState:
            output = (datetime.now(), tempLM35, tempDHT22, humidity,
                      mode, heater, heaterFrom, heaterTo, light)
            output = "%s,%.2f,%.2f,%.2f,%d,%d,%.1f,%.1f,%d" % output

            try: # output
                flog = open(LOGFILE, "a")
                flog.write(output + "\n")
            except: traceback.print_exc()
            if flog: flog.close()
            print output

            timemark = datetime.now()
            lastState = state

###############################################################################
