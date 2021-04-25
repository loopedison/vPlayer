# !/usr/bin/env python3
# -*- coding: utf-8 -*-
# Filename  : vPlayer.py
# Author    : Loopedison
# Date      : 20210425
# ==============================================================================
import os
import sys
import json
import time
import socket
import struct
import subprocess
import threading
import operator
import logging
import getopt

# ==============================================================================
# Global values
_GENV = {'ConfigDict':{}, 'TaskDict':{'TaskList':[], 'TaskNow':[],}}
# Motion Struct
_msgMotion = bytearray([0x55,0xAA,0x00,0x00,0x14,0x01,0x00,0x01,0xFF,0xFF,0xFF,0xFF,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,    # =>head:16bytes, interval:4bytes
                        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00, # =>6axis:24bytes
                        0x00,0x00,0x00,0x00,0x00,0x00])  # =>12io&2AD:6bytes
# Motion reset
_msgReset = bytearray([0x55,0xAA,0x00,0x00,0x12,0x01,0x00,0x02,0xFF,0xFF,0xFF,0xFF,0x00,0x00,0x00,0x01,0x00,0x00])

# ==============================================================================
class vPlayer(object):
    def __init__(self, xServerIP=None, xServerPort=None, xServoIP=None, xServoPort=None, *args, **kwargs):
        # configure list
        self._vConfig = {'vPlayerWorkPath':None, 'MotionFilePath':None,
                        'ServerThread':None, 'ServerStatus':False, 'ServerSocket':None, 'ServerIP':None, 'ServerPort':None, 'ServerClients':[], 
                        'MainThread':None, 'MainStatus':False,
                        'MotionThread':None, 'MotionStatus':False, 'ServoSocket':None, 'ServoIP':None, 'ServoPort':None, 'ServoClients':[],
                        'vpStatus':'idle', 'vpIndex':'0', 'vpDelay':'0', 'vpStartT':'2000', 'vpStopT':'2000', 'vpMotionFile':None, 'vpTimeLst':0, 'vpTiming':0, 'vpTIMER':20,
                        'vpServoINT':0, 'vpServoParam':list(range(8)), 'vpServoData':list(range(8)),}
        self._vConfig['ServerIP'] = xServerIP if xServerIP else _GENV['ConfigDict'].get('ServerIP')
        self._vConfig['ServerPort'] = xServerPort if xServerPort else _GENV['ConfigDict'].get('ServerPort')
        self._vConfig['ServoIP'] = xServoIP if xServoIP else _GENV['ConfigDict'].get('ServoIP')
        self._vConfig['ServoPort'] = xServoPort if xServoPort else _GENV['ConfigDict'].get('ServoPort')
        self._vConfig['vPlayerWorkPath'] = os.getcwd()
        self._vConfig['MotionFilePath'] = _GENV['ConfigDict'].get('MotionFilePath')
        logging.info('vPlayer Work Path:[%s]' %(self._vConfig['vPlayerWorkPath']))
        logging.info('vMotion File Path:[%s]' %(self._vConfig['MotionFilePath']))
        logging.info('Server ListenAt:[%s,%s]' %(self._vConfig['ServerIP'],self._vConfig['ServerPort']))
        logging.info('Servo SendingTo:[%s,%s]' %(self._vConfig['ServoIP'],self._vConfig['ServoPort']))
    
    def ServerThreadHandle(self):
        # ======================================
        # ServerSocket handle, waiting for connections, then create thread
        # ======================================
        # Configure TCP server
        self._vConfig['ServerSocket'] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._vConfig['ServerSocket'].setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._vConfig['ServerSocket'].bind((self._vConfig['ServerIP'], int(self._vConfig['ServerPort'])))
        self._vConfig['ServerSocket'].listen(10)
        self._vConfig['ServerSocket'].setblocking(True)
        try:
            while self._vConfig['ServerStatus'] == True:
                cSocket,cAddr = self._vConfig['ServerSocket'].accept()
                cThread = threading.Thread(target=self.ServerClientThreadHandle, args=(cSocket,cAddr))
                cThread.setDaemon(True)
                cThread.start()
        finally:
            for sck,addr in self._vConfig['ServerClients']: sck.close()
            self._vConfig['ServerSocket'].close()
    
    def ServerClientThreadHandle(self, xSocket, xAddress):
        # ======================================
        # ServerClient handle
        # ======================================
        # TCP links
        logging.info('Server: [%s] connected!' %(str(xAddress)))
        self._vConfig['ServerClients'].append((xSocket,xAddress))
        try:
            while True:
                xMessage = xSocket.recv(1024)
                # ======================================
                # receive message error link is down
                if not xMessage : break
                # ======================================
                # receive message success and analysize message
                logging.info('Server Recv:[%s]:[%s]'%(str(xAddress), xMessage))
                xCommand = xMessage.decode('utf-8').lower().split()
                if xCommand[0] in ('vplayer'):
                    _GENV['TaskDict']['TaskList'].append((xSocket,xAddress,xCommand))
        finally:
            self._vConfig['ServerClients'].remove((xSocket, xAddress))
            xSocket.close()
            logging.info('Server: [%s] disconnected!' %(str(xAddress)))
    
    def MainThreadHandle(self):
        # ======================================
        # MainThread handle
        # ======================================
        # Analize Commander Message
        try:
            while self._vConfig['MainStatus'] == True:
                if len(_GENV['TaskDict']['TaskList']) > 0:
                    (xSck,xAddr,xCmd) = _GENV['TaskDict']['TaskList'].pop(0)
                    try:
                        opts,args = getopt.getopt(xCmd[1:], 'n:t:', ['help','opt=',])
                    except getopt.GetoptError:
                        logging.info('MainThread: getopt error!')
                    # Analize avgvs
                    t_vpOption = 'idle'
                    t_vpIndex = '0'
                    t_vpDelay = '0'
                    for opt,arg in opts:
                        if opt in ('--help'):
                            t_vpOption = 'help'
                        elif opt in ('--opt'):
                            t_vpOption = arg
                        elif opt in ('-n'):
                            t_vpIndex = arg
                        elif opt in ('-t'):
                            t_vpDelay = arg
                    # Analize tasks
                    try:
                        if t_vpOption == 'help':
                            xSck.send(("vplayer --opt=<'start','stop'> [-n=<Motion Num(int)> -t=<Motion Delay(int)>]\r\n" +
                                        "usage: vplayer --opt start -n 1 -t 2000\r\n" +
                                        "usage: vplayer --opt stop\r\n").encode('utf-8'))
                        elif t_vpOption == 'start':
                            if self._vConfig['vpStatus'] == 'idle':
                                if int(t_vpIndex) > 0 and int(t_vpDelay) >= 0:
                                    self._vConfig['vpStatus'] = t_vpOption
                                    self._vConfig['vpIndex'] = t_vpIndex
                                    self._vConfig['vpDelay'] = t_vpDelay
                                    xSck.send('vplayer --result OK\r\n'.encode('utf-8'))
                                else:
                                    xSck.send('vplayer --result Err03\r\n'.encode('utf-8'))
                            elif self._vConfig['vpStatus'] != 'idle':
                                xSck.send('vplayer --result Err04\r\n'.encode('utf-8'))
                        elif t_vpOption == 'stop':
                            if self._vConfig['vpStatus'] == 'running':
                                self._vConfig['vpStatus'] = t_vpOption
                                xSck.send('vplayer --result OK\r\n'.encode('utf-8'))
                            else:
                                xSck.send('vplayer --result Err04\r\n'.encode('utf-8'))
                        else:
                            # Undefined ERROR
                            xSck.send('vplayer --result Err02\r\n'.encode('utf-8'))
                    except ValueError:
                        xSck.send('vplayer --result Err01\r\n'.encode('utf-8'))
        finally:
            pass
    
    def MotionThreadHandle(self):
        # ======================================
        # MotionThread handle, 
        # ======================================
        # Configure UDP server
        self._vConfig['ServoSocket'] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._vConfig['vpTimeLst'] = time.time()
        self._vConfig['vpTiming'] = 0
        # ======================================
        try:
            while self._vConfig['MotionStatus'] == True:
                # ======================================
                # For Timer function ~20ms
                if time.time() < (self._vConfig['vpTimeLst'] + self._vConfig['vpTiming']*float(self._vConfig['vpTIMER']/1000)): continue
                # ======================================
                # Control servo UDP
                self._vConfig['vpTiming'] += 1
                if self._vConfig['vpStatus'] == 'idle':
                    pass
                elif self._vConfig['vpStatus'] == 'start':
                    # ======================================
                    # Receive 'start'; Start initial
                    if self._vConfig['vpIndex'] == '0':
                        self._vConfig['vpStatus'] = 'idle'
                    else:
                        try:
                            self._vConfig['vpMotionFile'] = open(self._vConfig['MotionFilePath']+'/'+'Game_'+self._vConfig['vpIndex']+'.csv', 'r')
                            self._vConfig['vpTimeLst'] = time.time()
                            self._vConfig['vpTiming'] = 0
                            self._vConfig['vpStatus'] = 'ready'
                            logging.info('Servo: Playing [No.%s]' %(self._vConfig['vpIndex']))
                        except:
                            self._vConfig['vpStatus'] = 'idle'
                            logging.error('Servo: Open MotionFile failed!')
                elif self._vConfig['vpStatus'] == 'ready':
                    # ======================================
                    # Receive 'ready'; Prepare Platform
                    self._vConfig['vpServoINT'] = int(self._vConfig['vpStartT'])
                    _msgMotion[16:20] = struct.pack('>I', int(self._vConfig['vpServoINT']))
                    self._vConfig['vpServoData'][1] = (0.5)*float(_GENV['ConfigDict']['MotionTrip'])*10000/float(_GENV['ConfigDict']['MotionLead'])
                    self._vConfig['vpServoData'][2] = (0.5)*float(_GENV['ConfigDict']['MotionTrip'])*10000/float(_GENV['ConfigDict']['MotionLead'])
                    self._vConfig['vpServoData'][3] = (0.5)*float(_GENV['ConfigDict']['MotionTrip'])*10000/float(_GENV['ConfigDict']['MotionLead'])
                    self._vConfig['vpServoData'][4] = (0.5)*float(_GENV['ConfigDict']['MotionTrip'])*10000/float(_GENV['ConfigDict']['MotionLead'])
                    self._vConfig['vpServoData'][5] = (0.5)*float(_GENV['ConfigDict']['MotionTrip'])*10000/float(_GENV['ConfigDict']['MotionLead'])
                    self._vConfig['vpServoData'][6] = (0.5)*float(_GENV['ConfigDict']['MotionTrip'])*10000/float(_GENV['ConfigDict']['MotionLead'])
                    _msgMotion[20:24] = struct.pack('>I', int(self._vConfig['vpServoData'][_GENV['ConfigDict']['MotionSequence']['A1']]))
                    _msgMotion[24:28] = struct.pack('>I', int(self._vConfig['vpServoData'][_GENV['ConfigDict']['MotionSequence']['A2']]))
                    _msgMotion[28:32] = struct.pack('>I', int(self._vConfig['vpServoData'][_GENV['ConfigDict']['MotionSequence']['A3']]))
                    _msgMotion[32:36] = struct.pack('>I', int(self._vConfig['vpServoData'][_GENV['ConfigDict']['MotionSequence']['A4']]))
                    _msgMotion[36:40] = struct.pack('>I', int(self._vConfig['vpServoData'][_GENV['ConfigDict']['MotionSequence']['A5']]))
                    _msgMotion[40:44] = struct.pack('>I', int(self._vConfig['vpServoData'][_GENV['ConfigDict']['MotionSequence']['A6']]))
                    self._vConfig['ServoSocket'].sendto(_msgMotion, (self._vConfig['ServoIP'], int(self._vConfig['ServoPort'])))
                    self._vConfig['vpStatus'] = 'running'
                elif self._vConfig['vpStatus'] == 'running':
                    # ======================================
                    # When 'running'; Sending Motion Data
                    if self._vConfig['vpTiming'] >= (int(self._vConfig['vpStartT']) + int(self._vConfig['vpDelay']))/self._vConfig['vpTIMER']:
                        try:
                            rawData = self._vConfig['vpMotionFile'].readline()
                            if rawData:
                                self._vConfig['vpServoParam'] = rawData.strip('\n').split(',')
                                if self._vConfig['vpServoParam'][0] != '' and float(self._vConfig['vpServoParam'][0]) != 0:
                                    self._vConfig['vpServoINT'] = self._vConfig['vpTIMER']
                                    _msgMotion[16:20] = struct.pack('>I', int(self._vConfig['vpServoINT']))
                                    self._vConfig['vpServoData'][1] = (0.5+float(self._vConfig['vpServoParam'][1]))*float(_GENV['ConfigDict']['MotionTrip'])*10000/float(_GENV['ConfigDict']['MotionLead'])
                                    self._vConfig['vpServoData'][2] = (0.5+float(self._vConfig['vpServoParam'][2]))*float(_GENV['ConfigDict']['MotionTrip'])*10000/float(_GENV['ConfigDict']['MotionLead'])
                                    self._vConfig['vpServoData'][3] = (0.5+float(self._vConfig['vpServoParam'][3]))*float(_GENV['ConfigDict']['MotionTrip'])*10000/float(_GENV['ConfigDict']['MotionLead'])
                                    self._vConfig['vpServoData'][4] = (0.5+float(self._vConfig['vpServoParam'][4]))*float(_GENV['ConfigDict']['MotionTrip'])*10000/float(_GENV['ConfigDict']['MotionLead'])
                                    self._vConfig['vpServoData'][5] = (0.5+float(self._vConfig['vpServoParam'][5]))*float(_GENV['ConfigDict']['MotionTrip'])*10000/float(_GENV['ConfigDict']['MotionLead'])
                                    self._vConfig['vpServoData'][6] = (0.5+float(self._vConfig['vpServoParam'][6]))*float(_GENV['ConfigDict']['MotionTrip'])*10000/float(_GENV['ConfigDict']['MotionLead'])
                                    _msgMotion[20:24] = struct.pack('>I', int(self._vConfig['vpServoData'][_GENV['ConfigDict']['MotionSequence']['A1']]))
                                    _msgMotion[24:28] = struct.pack('>I', int(self._vConfig['vpServoData'][_GENV['ConfigDict']['MotionSequence']['A2']]))
                                    _msgMotion[28:32] = struct.pack('>I', int(self._vConfig['vpServoData'][_GENV['ConfigDict']['MotionSequence']['A3']]))
                                    _msgMotion[32:36] = struct.pack('>I', int(self._vConfig['vpServoData'][_GENV['ConfigDict']['MotionSequence']['A4']]))
                                    _msgMotion[36:40] = struct.pack('>I', int(self._vConfig['vpServoData'][_GENV['ConfigDict']['MotionSequence']['A5']]))
                                    _msgMotion[40:44] = struct.pack('>I', int(self._vConfig['vpServoData'][_GENV['ConfigDict']['MotionSequence']['A6']]))
                                    self._vConfig['ServoSocket'].sendto(_msgMotion, (self._vConfig['ServoIP'], int(self._vConfig['ServoPort'])))
                            else:
                                self._vConfig['vpMotionFile'].close()
                                self._vConfig['vpStatus'] = 'stop'
                        except Exception as e:
                            logging.error('Servo: SEND ERROR=>', end=''); logging.info(e)
                            self._vConfig['vpMotionFile'].close()
                            self._vConfig['vpStatus'] = 'stop'
                elif self._vConfig['vpStatus'] == 'stop':
                    # ======================================
                    # Receive 'stop'; Reset Platform
                    self._vConfig['vpStatus'] = 'reset'
                    self._vConfig['vpTimeLst'] = time.time()
                    self._vConfig['vpTiming'] = 0
                    self._vConfig['ServoSocket'].sendto(_msgReset, (self._vConfig['ServoIP'], int(self._vConfig['ServoPort'])))
                elif self._vConfig['vpStatus'] == 'reset':
                    # ======================================
                    # Receive 'Reset'; waiting
                    if self._vConfig['vpTiming'] >= int(self._vConfig['vpStopT'])/self._vConfig['vpTIMER']:
                        self._vConfig['vpStatus'] = 'idle'
                pass
            pass
        finally:
            self._vConfig['ServoSocket'].close()
    
    def run(self):
        self._vConfig['ServerStatus'] = True
        self._vConfig['ServerThread'] = threading.Thread(target=self.ServerThreadHandle)
        self._vConfig['ServerThread'].setDaemon(True)
        self._vConfig['ServerThread'].start()
        self._vConfig['MotionStatus'] = True
        self._vConfig['MotionThread'] = threading.Thread(target=self.MotionThreadHandle)
        self._vConfig['MotionThread'].setDaemon(True)
        self._vConfig['MotionThread'].start()
        self._vConfig['MainStatus'] = True
        self._vConfig['MainThread'] = threading.Thread(target=self.MainThreadHandle)
        self._vConfig['MainThread'].setDaemon(True)
        self._vConfig['MainThread'].start()
    def stop(self):
        self._vConfig['ServerStatus'] = False
        self._vConfig['MotionStatus'] = False
        self._vConfig['MainStatus'] = False

# ==============================================================================
if __name__ == "__main__":
    logging.info('vPlayer: Testing ...')
    with open('./config/'+'vPlayerConfig.json', 'r', encoding='utf-8') as confList:
        _GENV['ConfigDict'] = json.load(confList)
    xPlayer = vPlayer('10.0.0.15','9527','10.0.0.15','7408')
    xPlayer.run()
    time.sleep(120)
    xPlayer.stop()
