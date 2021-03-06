# -*- coding: utf-8 -*-
#########################################################################################
# Cactus Tracker v1.0.9 / March 22, 2015
# by Maksym Ganenko <buratin.barabanus at Google Mail>
#########################################################################################

import io, os, re, traceback
import BaseHTTPServer, urlparse, base64
import dateutil.parser
import matplotlib, numpy
from matplotlib import pylab
from matplotlib.ticker import AutoMinorLocator
from matplotlib.colors import rgb2hex
from datetime import datetime, timedelta
from itertools import groupby

HOST            = "stepan.local"
PORT            = 8080
USERNAME        = "cactus"
PASSWORD        = "forever"

LOGFILE         = "cactuslog.txt"
CMDFILE         = "cactuscmd.txt"

FONT            = "Arial"
FONT_SIZE       = 12

STATS_DAYS_NUM  = 7
SMOOTH_WINDOW   = 11
CURVE_ALPHA     = [1.0, 0.5, 0.25, 0.1]

MAGIC           = 10101

# time difference in seconds between real time and log time
LOG_TIME_OFFSET_SEC = 3600

OFF, ON, AUTO = 0, 1, 2

#########################################################################################

class CactusHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_GET(self):
        if not self.authorize(): return

        url = urlparse.urlparse(self.path)
        query = urlparse.parse_qs(url.query)

        pending, smooth = False, SMOOTH_WINDOW
        if "mode" in query and "hfrom" in query and "hto" in query and "light" in query:
            pending = True
            try:
                mode = int(query["mode"][0])
                heaterFrom = float(query["hfrom"][0])
                heaterTo = float(query["hto"][0])
                light = int(query["light"][0])
                self.update_params(mode, heaterFrom, heaterTo, light)
            except:
                traceback.print_exc()
        if "smooth" in query:
            try:
                smooth = int(query["smooth"][0])
            except:
                traceback.print_exc()            

        if self.path in [ "/cactus.png", "/favicon.ico" ]:
            self.send_image(self.path)
        else:
            self.send_page(pending, smooth)
        self.wfile.close()

    def authorize(self):
        if self.headers.getheader("Authorization") == None:
            return self.send_auth()
        else:
            auth = self.headers.getheader("Authorization")
            code = re.match(r"Basic (\S+)", auth)
            if not code: return self.send_auth()
            data = base64.b64decode(code.groups(0)[0])
            code = re.match(r"(.*):(.*)", data)
            if not code: return self.send_auth()
            user, password = code.groups(0)[0], code.groups(0)[1]
            if user != USERNAME or password != PASSWORD:
                return self.send_auth()
        return True

    def send_auth(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", "Basic realm=\"Cactus\"")
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.send_default()
        self.wfile.close()
        return False

    def send_default(self):
        self.wfile.write("""
        <html>
            <body style="background:url(data:image/png;base64,{imageCode}) repeat;">
            </body>
        </html>""".format(imageCode = "iVBORw0KGgoAAAANSUhEUgAAAAYAAAAGCAYAAADgzO9IAAA" +
                        "AJ0lEQVQIW2NkwA7+M2IR/w8UY0SXAAuCFCNLwAWRJVAEYRIYgiAJALsgBgYb" +
                        "CawOAAAAAElFTkSuQmCC"))

    def address_string(self):
        host, port = self.client_address[:2]
        return host

    def update_params(self, mode, heaterFrom, heaterTo, light):
        if max(mode, heaterFrom, heaterTo) >= MAGIC:
            print "invalid params values"
            return
        fout = open(CMDFILE, "w")
        fout.write("%d %d %.1f %.1f %d" % (MAGIC, mode, heaterFrom, heaterTo, light))
        fout.close()

    def send_image(self, path):
        filename = os.path.basename(path)
        name, ext = os.path.splitext(filename)
        fimage = open(filename)
        self.send_response(200)
        format = { ".png" : "png", ".ico" : "x-icon" }
        aDay = timedelta(days = 1)
        now = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
        expires = (datetime.now() + aDay).strftime('%a, %d %b %Y %H:%M:%S GMT')
        self.send_header("Content-type", "image/" + format[ext])
        self.send_header("Cache-Control", "public, max-age=" + str(aDay.total_seconds()))
        self.send_header("Date", now)
        self.send_header("Expires", expires)
        self.send_header("Content-length", os.path.getsize(filename))
        self.end_headers()
        self.wfile.write(fimage.read())
        fimage.close()

    def fix_time(self, X):
        time = X[0].timetuple()
        if time.tm_hour == 0 and time.tm_min <= 11:
            X[0] -= timedelta(seconds = time.tm_min * 60 + time.tm_sec)
        time = X[-1].timetuple()
        if time.tm_hour == 23 and time.tm_min >= 49:
            offset = (60 - time.tm_min - 1) * 60 + (60 - time.tm_sec - 1)
            X[-1] += timedelta(seconds = offset)

    def make_smooth(self, Y, winSize):
        winSize = min(winSize, len(Y) - 2)
        if winSize <= 0: return list(Y)
        Y = [ 2 * Y[0] - foo for foo in reversed(Y[1:winSize + 1]) ] + list(Y) \
          + [ 2 * Y[-1] - foo for foo in reversed(Y[-winSize - 1:-1]) ]
        window = numpy.ones(winSize * 2 + 1) / float(winSize * 2 + 1)
        Y = numpy.convolve(Y, window, 'same')
        Y = Y[winSize:-winSize]
        return list(Y)

    def generate_graph(self, data, title, **args):
        smooth, height = args["smooth"], args["height"]
        nbins, grey, minor = args["nbins"], args["grey"], args["minor"]

        nowDate = datetime.now().date()
        matplotlib.rc("font", family = FONT, size = FONT_SIZE)
        figure = pylab.figure(figsize = (964 / 100.0, height / 100.0), dpi = 100)

        stats = [ ]
        for date, points in groupby(data, lambda foo: foo[0].date().isoformat()):
            X, Y, H = zip(*points)
            deltaDays = (nowDate - X[0].date()).days

            if deltaDays >= STATS_DAYS_NUM: continue
            if len(X) == 1: continue

            # convert to same day data
            alpha = CURVE_ALPHA[min(len(CURVE_ALPHA) - 1, deltaDays)]
            tempColor = grey and rgb2hex((1 - alpha, 1 - alpha, 1 - alpha)) \
                              or rgb2hex((1 - alpha, 1 - alpha, 1))
            heaterColor = rgb2hex((1, 1 - alpha, 1 - alpha))
            X = [ datetime.combine(nowDate, foo.time()) for foo in X ]
            self.fix_time(X)
                        
            if deltaDays < len(CURVE_ALPHA) - 1:
                # make smooth and draw
                start = 0
                for heater, group in groupby(zip(Y, H), lambda foo: foo[1]):
                    finish = start + len(list(group))

                    XS = X[start:finish + 1]
                    if heater:
                        # YS = Y[start:finish + 1]
                        YS = self.make_smooth(Y[start:finish + 1], smooth)
                    elif finish + 1 - start < smooth:
                        winSize = (finish + 1 - start) / 2
                        YS = self.make_smooth(Y[start:finish + 1], winSize)
                    else:
                        YS = self.make_smooth(Y[start:finish + 1], smooth)
                    
                    pylab.plot(XS, YS, linewidth = 2,
                        color = heater and heaterColor or tempColor)

                    start = finish
            else:
                for i in range(3):
                    Y = self.make_smooth(Y, smooth)
                self.fix_time(X)
                stats.append((X, Y))

                # plot stats curve
                if deltaDays == len(CURVE_ALPHA) - 1:
                    X0, Y0 = stats.pop(0)
                    for curve in stats:
                        X1, Y1 = curve
                        pylab.fill(X0 + list(reversed(X1)), Y0 + list(reversed(Y1)),
                                   color = tempColor)

        pylab.ylabel(title)

        ax = pylab.axes()
        ax.xaxis_date()
        ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M"))
        ax.xaxis.set_major_locator(matplotlib.dates.HourLocator())
        ax.yaxis.get_major_locator().set_params(integer = True, nbins = nbins)

        ticks = ax.yaxis.get_major_locator().bin_boundaries(*ax.get_ylim())
        if len(ticks) >= 2 and round(ticks[1] - ticks[0]) > 1:
            step = int(round(ticks[1] - ticks[0]))
            ax.yaxis.grid(True, "minor")
            ax.yaxis.set_minor_locator(AutoMinorLocator(n = step))
        ax.tick_params(axis = "both", which = "both", direction = "out", labelright = True)
        ax.tick_params(axis = "x", which = "major", labelsize = 8)
        ax.grid(which = "major", alpha = 1.0)
        ax.grid(which = "minor", alpha = minor and 1.0 or 0.0)
        pylab.gcf().autofmt_xdate()
        pylab.tight_layout()

        image = io.BytesIO()
        pylab.savefig(image, format = "png")
        pylab.close(figure)
        image.seek(0)
        result = "<img src='data:image/png;base64,%s'/>" % \
                 base64.b64encode(image.getvalue())
        image.close()
        return result

    def send_page(self, pending, smooth):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        dataTemp, dataHumidity, flog = [ ], [ ], None

        while not flog:
            try:    flog = open(LOGFILE)
            except: traceback.print_exc()

        mode, heater, heaterFrom, heaterTo, humidity, light = AUTO, 0, 5, 10, None, OFF
        for s in flog:
            row = tuple(s.strip().split(","))
            offset = timedelta(seconds = LOG_TIME_OFFSET_SEC)
            date = dateutil.parser.parse(row[0]) + offset
            temp = float(row[1])
            if len(row) == 3:
                heater = int(row[2])
            elif len(row) == 6:
                mode, heater = int(row[2]), int(row[3])
                heaterFrom, heaterTo = float(row[4]), float(row[5])
            elif len(row) == 7:
                humidity = float(row[2])
                mode, heater = int(row[3]), int(row[4])
                heaterFrom, heaterTo = float(row[5]), float(row[6])
            elif len(row) == 8:
                humidity = float(row[3])
                mode, heater = int(row[4]), int(row[5])
                heaterFrom, heaterTo = float(row[6]), float(row[7])
            elif len(row) == 9:
                humidity = float(row[3])
                mode, heater = int(row[4]), int(row[5])
                heaterFrom, heaterTo = float(row[6]), float(row[7])
                light = int(row[8])
            dataTemp.append((date, temp, heater))
            dataHumidity.append((date, humidity, 0))

        graphTemp = self.generate_graph(dataTemp, u"Temperature, °C",
                    smooth = smooth, height = 350, nbins = 11, minor = True, grey = False)
        graphHumidity = self.generate_graph(dataHumidity, u"Humidity, %",
                    smooth = smooth, height = 200, nbins = 5, minor = False, grey = True)

        pending = pending or os.path.isfile(CMDFILE)
        self.wfile.write(re.sub(r"{\s", r"{{ ", re.sub(r"\s}", r" }}", """
<html>
    <head>
        <title>Cactus Tracker</title>
        <meta http-equiv="refresh" content="{refresh};URL='/'">
        <style>
            body {
                font-family: {font}, sans-serif; font-size: {fontSize}pt; 
                width: 964px; margin: 47px 30px 0 30px; padding: 0;
                background-color: white; color: #262626;
            }
            h1 {
                font-size: 24pt; margin: 0; padding-bottom: 4px; 
                border-bottom: 2px dotted #262626; margin-bottom: 26px;
            }
            input { 
                font-family: {font}, sans-serif; font-size: {fontSize}pt;
                border: 2px solid #262626; padding: 2px 6px;
            }
            button { 
                font-family: {font}, sans-serif; font-size: {fontSize}pt;
                padding: 4px 8px; border: 2px solid #262626; border-radius: 10px;
                background-color: white; color: #262626; margin: 0 3px;
            }
            form { display: inline-block; margin: 0; }
            .selected, button:hover:not([disabled]) {
                cursor: pointer; background-color: #262626; color: white;
            }
            .selected:hover { cursor: default; }
            .control { margin-top: 7px; margin-left: 70px; }
            .control td { padding-right: 25px; }
            .heater { width: 50px; text-align: center; margin: 0 3px; }
            .pending { opacity: 0.5; }
            .hidden { visibility: hidden; }
        </style>
    </head>
    <body>
        <h1>Cactus Tracker</h1>
        <div>{graphTemp}</div>
        <div style="margin-top: -15px;">{graphHumidity}</div>
        <div class="control">
            <form action="/" class="{pending}">
                <button type="submit"
                        style="visibility: hidden;" {disabled}></button>

                <table width="100%" cellspacing=0 cellpadding=0 border=0>
                    <tr>
                        <td>
                            Light:

                            <button type="submit" name="light"
                                    class="{lightOn}"   value="1" {disabled}> on   </button>
                            <button type="submit" name="light"
                                    class="{lightOff}"  value="0" {disabled}> off  </button>
                        </td>

                        <td>
                            Heater:

                            <button type="submit" name="mode"
                                    class="{modeOn}"   value="1" {disabled}> on   </button>
                            <button type="submit" name="mode"
                                    class="{modeOff}"  value="0" {disabled}> off  </button>
                            <button type="submit" name="mode"
                                    class="{modeAuto}" value="2" {disabled}> auto </button>
                        </td>

                        <td>
                            <span class="{heaterAuto}">
                                heat from
                                <input name="hfrom" class="heater" maxlength=2
                                       value="{heaterFrom:.0f}" {disabled}/>
                                to <input name="hto" class="heater" maxlength=2
                                       value="{heaterTo:.0f}" {disabled}/>
                                &deg;C
                            </span>
                        </td>

                        <td style="opacity: 0.5;" align=right>
                            The last {days} days are shown
                        </td>
                    </tr>
                </table>

                <input type="hidden" name="light" value="{light}"/>
                <input type="hidden" name="mode" value="{mode}"/>
                <input type="hidden" name="hfrom" value="{heaterFrom:.0f}"/>
                <input type="hidden" name="hto" value="{heaterTo:.0f}"/>
            </form>
        </div>
        <div style="position: absolute; top: 7px; left: 760px;">
            <img src="cactus.png">
        </div>
    </body>
</html>
""")).format(
    font            = FONT,
    fontSize        = FONT_SIZE,
    days            = STATS_DAYS_NUM,
    graphTemp       = graphTemp,
    graphHumidity   = graphHumidity,
    mode            = mode,
    heaterFrom      = heaterFrom,
    heaterTo        = heaterTo,
    modeOff         = (mode == OFF) and "selected" or "",
    modeOn          = (mode == ON) and "selected" or "",
    modeAuto        = (mode == AUTO) and "selected" or "",
    light           = light,
    lightOn         = (light == ON) and "selected" or "",
    lightOff        = (light == OFF) and "selected" or "",
    refresh         = pending and "20" or "1200",
    disabled        = pending and "disabled=true" or "",
    pending         = pending and "pending" or "",
    heaterAuto      = (mode != AUTO) and "hidden" or ""))

#########################################################################################

server = BaseHTTPServer.HTTPServer((HOST, PORT), CactusHandler)
server.serve_forever()

#########################################################################################