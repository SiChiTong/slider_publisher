#!/usr/bin/python
import rospy
import yaml
import sys
import os
from python_qt_binding.QtWidgets import QApplication, QWidget, QVBoxLayout,QHBoxLayout,QGridLayout, QLabel, QSlider, QLineEdit, QPushButton
from python_qt_binding.QtCore import Signal, Qt,  pyqtSlot
from python_qt_binding.QtGui import QFont
from threading import Thread
import signal

RANGE = 1000

class Publisher:
    def __init__(self, topic, msg, d):
        self.topic = topic
        self.msg = msg()
        self.pub = rospy.Publisher(topic, msg, queue_size=1)        
            
        # init map from GUI to message
        self.map = {}
        to_remove = []
        for key in d:
            if type(d[key]) == dict:
                self.map[key] = d[key]['to']
                d[key].pop('to')
            else:
                if key != 'type':
                    # init non-zero defaults
                    self.write(self.msg, key, d[key])
                to_remove.append(key)
        for rm in to_remove:
            d.pop(rm)
                                    
    def write(self,msg, key, val):
        if '.' in key:
            # get 1st field
            idx = key.find('.')
            self.write(getattr(msg, key[:idx]), key[idx+1:], val)
        elif '[' in key:
            field, idx = key[:-1].split('[')
            idx = int(idx)
            current = getattr(msg, field)
            if len(current) <= idx:
                current = [0 for i in range(idx+1)]
            current[idx] = val
            setattr(msg, field, current)
        else:
            setattr(msg, key, val)
        
    def update(self, values):
        for key in self.map:
            self.write(self.msg, self.map[key], values[key]['val'])
        # update time if stamped msg
        if hasattr(self.msg, "header"):
            self.write(self.msg, 'header.stamp', rospy.Time.now())
        self.pub.publish(self.msg)


class SliderPublisher(QWidget):
    def __init__(self, content):
        super(SliderPublisher, self).__init__()
        
        content = content.replace('\t', '    ')
        
        # get message types
        self.publishers = {}
        self.values = {}
        pkgs = []
        
        # to keep track of key ordering in the yaml file
        order = []
        old = []
         
        for topic, info in yaml.load(content).items():
            pkg,msg = info['type'].split('/')
            pkgs.append(__import__(pkg, globals(), locals(), ['msg']))
            self.publishers[topic] = Publisher(topic, getattr(pkgs[-1].msg, msg), info)
            order.append((topic,[]))
            for key in info:
                self.values[key] = info[key]
                order[-1][1].append((content.find(' ' + key + ':'), key))
                old.append((content.find(' ' + key + ':'), key))
                for bound in ['min', 'max']:
                    self.values[key][bound] = float(self.values[key][bound])
                self.values[key]['val'] = 0
            order[-1][1].sort()
        order.sort(key = lambda x: x[1][0][0])
        # build sliders - thanks joint_state_publisher
        sliderUpdateTrigger = Signal()
        self.vlayout = QVBoxLayout(self)
        self.gridlayout = QGridLayout()
        font = QFont("Helvetica", 9, QFont.Bold)
        topic_font = QFont("Helvetica", 10, QFont.Bold)
        
        sliders = []
        self.key_map = {}
        y = 0
        for topic,keys in order:
            topic_layout = QVBoxLayout()
            label = QLabel(topic)
            label.setFont(topic_font)
            topic_layout.addWidget(label)
            self.gridlayout.addLayout(topic_layout, *(y, 0))
            y+=1
            for idx,key in keys:           
                key_layout = QVBoxLayout()
                row_layout = QHBoxLayout()
                label = QLabel(key)
                label.setFont(font)
                row_layout.addWidget(label)
                
                display = QLineEdit("0.00")
                display.setAlignment(Qt.AlignRight)
                display.setFont(font)
                display.setReadOnly(True)
                
                row_layout.addWidget(display)    
                key_layout.addLayout(row_layout)
                
                slider = QSlider(Qt.Horizontal)
                slider.setFont(font)
                slider.setRange(0, RANGE)
                slider.setValue(RANGE/2)
                
                key_layout.addWidget(slider)
            
                self.key_map[key] = {'slidervalue': 0, 'display': display, 'slider': slider}
                slider.valueChanged.connect(self.onValueChanged)
                self.gridlayout.addLayout(key_layout, *(y,0))
                y+=1
                #sliders.append(key_layout)
        
            # Generate positions in grid and place sliders there
            #self.positions = [(y,0) for y in range(len(sliders))]
            #for item, pos in zip(sliders, self.positions):
            #    self.gridlayout.addLayout(item, *pos)
            
        self.vlayout.addLayout(self.gridlayout)            
        
        self.ctrbutton = QPushButton('Center', self)
        self.ctrbutton.clicked.connect(self.center)
        self.vlayout.addWidget(self.ctrbutton)
            
        self.center(1)
        
    def sliderToValue(self, slider, key):
        val = self.values[key]
        return val['min'] + slider*(val['max'] - val['min'])/RANGE            
        
    @pyqtSlot(int)
    def onValueChanged(self, event):
        # A slider value was changed, but we need to change the joint_info metadata.
        for key, key_info in self.key_map.items():
            key_info['slidervalue'] = key_info['slider'].value()
            # build corresponding value                        
            self.values[key]['val'] = self.sliderToValue(key_info['slidervalue'], key)    
            key_info['display'].setText("%.2f" % self.values[key]['val'])        
            
    def center(self, event):
        for key, key_info in self.key_map.items():
            key_info['slider'].setValue(RANGE/2)
        self.onValueChanged(event)
            
        
    def loop(self):        
        rate = rospy.Rate(10)
        while not rospy.is_shutdown():
            for pub in self.publishers:
                self.publishers[pub].update(self.values)
            rate.sleep()
            

if __name__ == "__main__":
    
    rospy.init_node('slider_publisher')
    
    # read passed param
    filename = sys.argv[-1]
    if not os.path.exists(filename):
        if not rospy.has_param("~file"):
            rospy.logerr("Pass a yaml file (~file param or argument)")
            sys.exit(0)
        filename = rospy.get_param("~file")
        
    
    # also get order from file
    with open(filename) as f:
        content = f.read()
                        
    # build GUI
    title = os.path.splitext(os.path.split(filename)[-1])[0]
    app = QApplication([title])    
    sp = SliderPublisher(content)
    Thread(target=sp.loop).start()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sp.show()
    sys.exit(app.exec_())

        
    
        
        
    
    
    
