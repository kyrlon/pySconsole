from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import pyqtProperty
import serial, time, sys
import queue, threading
import serial.tools.list_ports

hexmode     = False
SER_TIMEOUT = 0.1
class SerialGUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.__init_ui()

    def closeEvent(self, event):
        super().closeEvent(event)

    def __init_ui(self):
        self.serialInput_q, self.serialOut_q = queue.Queue(), queue.Queue() 
        
        self.setWindowTitle('Serial232')
        self.setWindowIcon(QtGui.QIcon('gtri_logo.png'))
        
        # Top Group
        
        #set combo box for serial ports
        self.portComboBox = SerialPortCombo()
        self.baudComboBox = BaudRateCombo()
        self.selectPortLbl = QtWidgets.QLabel("Port:")
        self.baudRateLbl = QtWidgets.QLabel("Baudrate:")
        self.connctButton = QtWidgets.QPushButton("Connect")
        self.connctButton.clicked.connect(self.port_connect)

        # Sets layout for GUI header/combo
        self.header_layout = QtWidgets.QGridLayout() #TODO: fix weird layout scheme
        self.header_layout.addWidget(self.selectPortLbl, 0, 0) 
        self.header_layout.addWidget(self.portComboBox, 0, 1)
        self.header_layout.addWidget(self.connctButton, 0, 2)
        self.header_layout.addWidget(self.baudRateLbl, 1, 0) 
        self.header_layout.addWidget(self.baudComboBox, 1, 1) 

        header_layout_wrapper = QtWidgets.QWidget()
        header_layout_wrapper.setLayout(self.header_layout)
        header_layout_wrapper.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)


        #Middle Group

        # set serial output from the device
        self.serial_output = QtWidgets.QTextBrowser()
        # self.serial_output.setStyleSheet("background-color: blue;")
        self.serial_output.setAcceptRichText(True)
        self.serial_output.setOpenExternalLinks(True)

        #set history log
        self.history_log = HistoryList()
        self.history_log.itemDoubleClicked.connect(self.history_item_selected)
        self.history_log.returnPressed.connect(self.history_item_selected)
        self.history_log.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection) #TODO add option to save log/restore

        # set layout for serial output and history #TODO: add checkbox for history log
        self.middle_layout = QtWidgets.QHBoxLayout()
        self.middle_layout.addWidget(self.serial_output)
        self.middle_layout.addWidget(self.history_log)
        middle_layout_wrapper = QtWidgets.QWidget()
        middle_layout_wrapper.setLayout(self.middle_layout)
        middle_layout_wrapper.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        # Lower Group
        # set layout for input stuff
        self.line_edit = QtWidgets.QLineEdit()
        self.line_edit.returnPressed.connect(self.populate_history)
        self.led_indicator = LedIndicator()
        self.led_indicator.setDisabled(True)
        self.lower_layout = QtWidgets.QHBoxLayout()
        self.lower_layout.addWidget(self.line_edit)
        self.line_label = QtWidgets.QLabel()
        self.lower_layout.addWidget(self.line_label)
        self.lower_layout.addWidget(self.led_indicator)


        lower_layout_wrapper = QtWidgets.QWidget()
        lower_layout_wrapper.setLayout(self.lower_layout)
        lower_layout_wrapper.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)


        # Sets full GUI layout
        gui_layout = QtWidgets.QVBoxLayout()
        gui_layout.addWidget(header_layout_wrapper)
        gui_layout.addWidget(middle_layout_wrapper)
        gui_layout.addWidget(lower_layout_wrapper)
        gui_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        gui_layout.setContentsMargins(QtCore.QMargins(0, 0, 0, 0))

        self.setLayout(gui_layout)


    def populate_history(self):
        if self.led_indicator.isChecked(): 
            self.serialInput_q.put(self.line_edit.text())
            self.history_log.addItem(self.line_edit.text())
            self.console_ouput()
            self.line_edit.clear()
        else:
            txt = "Please connect serial device!!"
            self.serial_output.append(txt)
            self.line_edit.clear()
    def history_item_selected(self):
        self.line_edit.setText(self.history_log.currentItem().text())

    def console_ouput(self): #TODO: FIX LAG OF output
        while not self.serialOut_q.empty():
            try:
                data = self.serialOut_q.get()
            except queue.Empty:
                data = "N/A"
            # print("DEBUGGIMG" + data)
            self.serial_output.append(data)

    def port_connect(self):
        if self.connctButton.text() == "Connect": #TODO: fix issue of serial errror
            p = self.portComboBox.getCurrentPort()
            self.serth = SerialCom(p, 115200, self.serialInput_q, self.serialOut_q)   # Start serial thread
            # self.serth = SerialCom("COM20", 115200, self.serialInput_q, self.serialOut_q)   # Start serial thread
            # self.serth = SerialCom("COM9", 9600, self.serialInput_q, self.serialOut_q)   # Start serial thread
            self.serth.Start()
            self.led_indicator.setChecked(True)
            self.connctButton.setText("Disconnect")
        else:
            if self.serth.connected:
                self.serth.Stop()
            self.connctButton.setText("Connect")
            self.led_indicator.setChecked(False)


# Convert a string to bytes
def str_bytes(s):
    return s.encode('latin-1')
     
# Convert bytes to string
def bytes_str(d):
    return d if type(d) is str else "".join([chr(b) for b in d])
     
# Return hexadecimal values of data
def hexdump(data):
    return " ".join(["%02X" % ord(b) for b in data])
 
# Return a string with high-bit chars replaced by hex values
def textdump(data):
    return "".join(["[%02X]" % ord(b) if b>'\x7e' else b for b in data])
     
# Display incoming serial data
def display(s):
    if not hexmode:
        print(textdump(str(s)))
        # sys.stdout.write(textdump(str(s)))
    else:
        print(hexdump(s) + ' ')

# Thread to handle incoming & outgoing serial data
class SerialCom:
    def __init__(self, portname, baudrate, serialInput, serialOut): # Initialise with serial port details
        self.portname, self.baudrate = portname, baudrate
        self.txq = serialInput
        self.rxq = serialOut
        self.running = False
        self.connected = False
        self._loop = True
        self._read_thread = threading.Thread(target=self.readData, daemon=True)
        # self._read_thread = QtCore.QThread(target=self.readData, daemon=True)
        self._send_thread = threading.Thread(target=self.sendData, daemon=True)
        self._read_thread.start()
        self._send_thread.start()
 
    def sendData(self):                   # Write outgoing data to serial port if open
        while self._loop:
            while self.running:
                cmd = self.txq.get()                     # ..using a queue to sync with reader thread
                # s = self.ser.read(self.ser.in_waiting or 1)
                cmd = (cmd + "\r")
                cmd = cmd.encode()
                _ = self.ser.write(cmd)
         
    def readData(self):                    # Write incoming serial data to screen
        while self._loop:
            while self.running:
                # s = self.ser.read(self.ser.in_waiting or 1)
                s = self.ser.readline()
                if s:                                       # Get data from serial port
                    data = bytes_str(s)               # ..and convert to string
                    if data != '':
                        self.rxq.put(data)               # ..and convert to string
                    display(s)
         
    def Start(self):                          # Run serial reader thread
        print("Opening %s at %u baud %s" % (self.portname, self.baudrate,
              "(hex display)" if hexmode else ""))
        try:
            self.ser = serial.Serial(port=self.portname, baudrate=self.baudrate)
            time.sleep(SER_TIMEOUT*1.2)
            self.ser.flushInput()
            self.running = True
            print(1)
        except Exception as e:
            self.ser = None
            print(e)
        if not self.ser:
            print("Can't open port")
            self.running = False
        self.connected = True
        print(2)

    def Stop(self):
        self.running = False
        self._loop = False
        self.connected = False
        self.ser.close()
        self.ser = None

class LedIndicator(QtWidgets.QAbstractButton):
    scaledSize = 1000.0

    def __init__(self):
        super().__init__()

        self.setMinimumSize(24, 24)
        self.setCheckable(True)

        # Green ON / Red OFF
        self.on_color_1 = QtGui.QColor(0, 255, 0)
        self.on_color_2 = QtGui.QColor(0, 192, 0)
        self.off_color_1 = QtGui.QColor(28, 0, 0)
        self.off_color_2 = QtGui.QColor(156, 0, 0)

    def resizeEvent(self, QResizeEvent):
        self.update()

    def paintEvent(self, QPaintEvent):
        realSize = min(self.width(), self.height())

        painter = QtGui.QPainter(self)
        pen = QtGui.QPen(QtCore.Qt.black)
        pen.setWidth(1)

        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(realSize / self.scaledSize, realSize / self.scaledSize)

        gradient = QtGui.QRadialGradient(QtCore.QPointF(-500, -500), 1500, QtCore.QPointF(-500, -500))
        gradient.setColorAt(0, QtGui.QColor(224, 224, 224))
        gradient.setColorAt(1, QtGui.QColor(28, 28, 28))
        painter.setPen(pen)
        painter.setBrush(QtGui.QBrush(gradient))
        painter.drawEllipse(QtCore.QPointF(0, 0), 500, 500)

        gradient = QtGui.QRadialGradient(QtCore.QPointF(500, 500), 1500, QtCore.QPointF(500, 500))
        gradient.setColorAt(0, QtGui.QColor(224, 224, 224))
        gradient.setColorAt(1, QtGui.QColor(28, 28, 28))
        painter.setPen(pen)
        painter.setBrush(QtGui.QBrush(gradient))
        painter.drawEllipse(QtCore.QPointF(0, 0), 450, 450)

        painter.setPen(pen)
        if self.isChecked():
            gradient = QtGui.QRadialGradient(QtCore.QPointF(-500, -500), 1500, QtCore.QPointF(-500, -500))
            gradient.setColorAt(0, self.on_color_1)
            gradient.setColorAt(1, self.on_color_2)
        else:
            gradient = QtGui.QRadialGradient(QtCore.QPointF(500, 500), 1500, QtCore.QPointF(500, 500))
            gradient.setColorAt(0, self.off_color_1)
            gradient.setColorAt(1, self.off_color_2)

        painter.setBrush(gradient)
        painter.drawEllipse(QtCore.QPointF(0, 0), 400, 400)

    @pyqtProperty(QtGui.QColor)
    def onColor1(self):
        return self.on_color_1

    @onColor1.setter
    def onColor1(self, color):
        self.on_color_1 = color

    @pyqtProperty(QtGui.QColor)
    def onColor2(self):
        return self.on_color_2

    @onColor2.setter
    def onColor2(self, color):
        self.on_color_2 = color

    @pyqtProperty(QtGui.QColor)
    def offColor1(self):
        return self.off_color_1

    @offColor1.setter
    def offColor1(self, color):
        self.off_color_1 = color

    @pyqtProperty(QtGui.QColor)
    def offColor2(self):
        return self.off_color_2

    @offColor2.setter
    def offColor2(self, color):
        self.off_color_2 = color

class BaudRateCombo(QtWidgets.QComboBox):
    def __init__(self) -> None:
        super().__init__()
        self.baudlist = ["2400", "4800", "9600", "19200", "38400", "57600", "115200"]
        self.addItems(self.baudlist)

class HistoryList(QtWidgets.QListWidget):
    returnPressed = QtCore.pyqtSignal()
    def __init__(self) -> None:
        super().__init__()
    
    def keyPressEvent(self, ev):
        super().keyPressEvent(ev)
        if ev.key() in (QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return):
            self.returnPressed.emit()
        


class SerialPortCombo(QtWidgets.QComboBox):
    def __init__(self) -> None:
        super().__init__()
        self.setEditable(True)

    def showPopup(self):
        super().showPopup()
        self.findPorts()

    def findPorts(self):
        dummy = False
        if not dummy:
            dev = []
            self.portDict = dict()
            self.clear()
            ports = serial.tools.list_ports.comports()
            for port, desc, hwid in sorted(ports):
                dev_hwinfo = "{}: {} [{}]".format(port, desc, hwid)
                dev.append(dev_hwinfo)
                self.portDict[dev_hwinfo] = {"port": port, "desc": desc, "hwid": hwid}
            self.addItems(dev)
        else:
            self.addItems(["1", "2", "3"] )

    def getCurrentPort(self):
        return self.portDict[self.currentText()]["port"]
    

    


if __name__ == "__main__":
    one = True
    t = False
    # func = True
    # zzz = True
    if one:
        current_port = 51234
        app = QtWidgets.QApplication([])
        player = SerialGUI()
        screensize = app.desktop().availableGeometry().size()
        # player.resize(screensize)
        player.show()

        exit(app.exec_())
    
    if t:

        ports = serial.tools.list_ports.comports()

        for port, desc, hwid in sorted(ports):
                print("{}: {} [{}]".format(port, desc, hwid))
    if zzz:
      while True:

        with serial.Serial(port="COM20",baudrate=115200) as s:
            print(1)
            cmd = input("Enter cmd: ")

            if not cmd:

                continue

            cmd = (cmd + "\r")

            cmd = cmd.encode()

            _ = s.write(cmd)

            print(s.readline())

            # print(s.readline())

    if func:
        def display(s):
            if not hexmode:
                # print(textdump(str(s)))
                sys.stdout.write(textdump(str(s)))
            else:
                print(hexdump(s) + ' ')

        txq = queue.Queue()
        def sendData(txq,s):                   # Write outgoing data to serial port if open
            txq.put(s)                     # ..using a queue to sync with reader thread
         
        def readData(s):                    # Write incoming serial data to screen
            display(s)
            print("ok")

        try:
            ser = serial.Serial(port="COM20", baudrate=9600)
            time.sleep(SER_TIMEOUT*1.2)
            ser.flushInput()
            print(1)
        except Exception as e:
            ser = None
            print(e)
        if not ser:
            print("Can't open port")
            running = False

        while running:
            s = ser.read(ser.in_waiting or 1)
            if s:                                       # Get data from serial port
                readData(bytes_str(s))               # ..and convert to string
            if not txq.empty():
                txd = str(txq.get())               # If Tx data in queue, write to serial port
                ser.write(str_bytes(txd))
        if ser:                                    # Close serial port when thread finished
            ser.close()
            ser = None