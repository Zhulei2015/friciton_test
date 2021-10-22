from PySide2.QtWidgets import *
from PySide2.QtUiTools import QUiLoader
from PySide2.QtCore import *
from PySide2.QtGui import QIcon, QPixmap, QKeySequence

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5 import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter
import numpy as np
import sys
import serial
import modbus_tk
import modbus_tk.defines as cst
from modbus_tk import modbus_rtu
import ctypes
import time
import pandas as pd



class WorkerSignals(QObject):
    '''
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        tuple (exctype, value, traceback.format_exc() )

    result
        object data returned from processing, anything

    progress
        int indicating % progress

    '''
    finished = Signal()
    error = Signal(tuple)
    result = Signal(list)
    progress = Signal(int)

class Worker(QRunnable):
    '''
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    '''

    def __init__(self, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        #
        self.is_paused=False
        self.is_killed=False

    @Slot()
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''
        begin_time=time.time()
        while self.is_killed == False:
            # 读保持寄存器
            # 1为从地址, cst.R...为读寄存器, 0为读取寄存器开始地址，9为读取寄存器的个数
            red = master.execute(1, cst.READ_HOLDING_REGISTERS, 0, 4)  # 这里可以修改需要读取的功能码
            print(red)
            load = weight(list(red))
            local_time = time.time()
            test_time = round(local_time-begin_time,2)
            time.sleep(0.2)
            self.signals.result.emit(list((load,test_time)))

            while self.is_paused:
               time.sleep(0)

        self.signals.finished.emit()  # Done

    def pause(self):
        if self.is_paused == False:
           self.is_paused = True
        else:
           self.is_paused = False

    def kill(self):
        self.is_killed = True


class Mainwindow(QMainWindow):

    def __init__(self):
        # 动态加载ui
        qfile_Con = QFile("modbus.ui")
        qfile_Con.open(QFile.ReadOnly)
        qfile_Con.close()
        self.ui = QUiLoader().load(qfile_Con)

        self.ui.Start.clicked.connect(self.readweight)
        self.ui.Connect.clicked.connect(lambda: self.connect_COM('COM3'))
        self.ui.Disconnect.clicked.connect(self.disconnect)
        self.ui.Savedata.clicked.connect(self.save_data)
        self.ui.Continue.setEnabled(False)
        self.ui.Start.setEnabled(False)
        self.ui.Stop.setEnabled(False)

        self.threadpool = QThreadPool()

        self.ui.Continue.clicked.connect(self.Continue_test)


    def connect_COM(self,PORT):

        PORT =self.ui.Comselect.currentText()

        if len(self.ui.Cominput.text()) != 0 :
            PORT=self.ui.Cominput.text()


        alarm = ""
        try:
            # 设定串口为从站
            global master
            master = modbus_rtu.RtuMaster(serial.Serial(port=PORT,
                                                        baudrate=9600,
                                                        bytesize=8,
                                                        parity='N',
                                                        stopbits=1))
            master.set_timeout(5.0)
            # debugger log open
            master.set_verbose(True)

            alarm = "正常"
            browser = self.ui.textBrowser
            browser.append(alarm+'成功连接！'+'串口：'+PORT)
            self.ui.Continue.setEnabled(True)
            self.ui.Start.setEnabled(True)
            return alarm

        except Exception as exc:
            print(str(exc))
            alarm = (str(exc))
            browser = self.ui.textBrowser
            browser.append(alarm)

        return alarm  ##如果异常就返回[],故障信息

    def disconnect(self):
        master._do_close()
        browser = self.ui.textBrowser
        browser.append('关闭连接！')
        return True

    def readweight(self):

        # 读保持寄存器
        # 1为从地址, cst.R...为读寄存器, 0为读取寄存器开始地址，9为读取寄存器的个数
        red = master.execute(1, cst.READ_HOLDING_REGISTERS, 0, 4)  # 这里可以修改需要读取的功能码
        print(red)
        load= weight(list(red))
        self.print_output(load)
        return list(red)
    test_time = []
    load_continue = []
    test_localtime = []

    def print_output(self,load):
        ''' print load in browser '''

        Localtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        if len(load)==1 :
            browser = self.ui.textBrowser
            browser.append('当前时间：'+Localtime+' 测试重量：'+str(load[0]))
        else:
            self.test_localtime.append(Localtime)
            browser = self.ui.textBrowser
            browser.append('当前时间：'+Localtime+' 测试重量：'+str(load[0][0])+' 测试时间：'+str(load[1]))


    def thread_complete(self):

        print("THREAD COMPLETE!")
        browser = self.ui.textBrowser
        browser.append('测试结束！')
        self.ui.Continue.setEnabled(True)


    def Continue_test(self):

        #

        try:
            self.verticalLayoutplot.count() !=0
        except:
            self.figure = Figure()
            self.canvas = FigureCanvas(self.figure)
            self.ax, self.ax1 = self.figure.subplots(1, 2)
            self.verticalLayoutplot = QVBoxLayout(self.ui.Plotarea)
            self.verticalLayoutplot.addWidget(self.canvas)
            self.verticalLayoutplot.addWidget(NavigationToolbar(self.canvas, self.ui))
        else:
            self.ax.cla()
            self.ax1.cla()
            self.test_time=[]
            self.load_continue=[]

        # Execute
        self.worker = Worker()
        self.threadpool.start(self.worker)
        self.worker.signals.result.connect(self.print_output)
        self.worker.signals.finished.connect(self.thread_complete)
        self.worker.signals.result.connect(self.test_plot)
        self.ui.Stop.clicked.connect(self.worker.kill)
        self.ui.Continue.setEnabled(False)
        self.ui.Stop.setEnabled(True)

    def test_plot(self,load):
        self.ax.cla()
        self.ax1.cla()
        self.test_time.append(load[1])
        self.load_continue.append(load[0][0])
        self.x = np.array(self.test_time)
        self.y = np.array(self.load_continue)
        self.ax.plot(self.x, self.y)
        self.Load_input=self.ui.Loadinput.text()
        self.y1= self.y/float(self.Load_input)
        self.ax1.plot(self.x, self.y1)
        self.ax.set_xlabel('Time (s)')
        self.ax.set_ylabel('Load (g)')
        self.ax1.set_xlabel('Time (s)')
        self.ax1.set_ylabel('friction [-]')
        self.canvas.draw()

    def save_data(self):
        self.data = np.column_stack((np.array(self.test_localtime),np.array(self.test_time)))
        self.data = np.column_stack((self.data, np.array(self.load_continue)))
        self.data = np.column_stack((self.data, np.array(self.y1)))
        self.data_pd = pd.DataFrame(self.data, columns=list(['测试时间','时间','重量','摩擦系数']))
        self.data_pd[['时间', '重量','摩擦系数']] = self.data_pd[['时间', '重量','摩擦系数']].apply(pd.to_numeric)
        self.data_pd.to_excel('friction_test_' + time.strftime("%Y年%m月%d日%H时%M分%S秒", time.localtime()) + '.xlsx', 'sheet1')

# 16位转10位
def hex2dec(v):
    return ctypes.c_int16(v).value

def weight(result):
    m1 = str(hex(result[0]))
    m2 = str(hex(result[1]))
    v = m2.split('x')[1] + m1.split('x')[1]
    v = int(v, 16)
    load = hex2dec(v)
    return list([load])


if __name__ == "__main__":
    app = QApplication([])
    mainwindow = Mainwindow()
    mainwindow.ui.show()
    app.exec_()
