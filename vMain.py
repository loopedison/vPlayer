# !/usr/bin/env python3
# -*- coding: utf-8 -*-
# Filename  : vMain.py
# Author    : Loopedison
# Date      : 20210425
# ==============================================================================

import os
import sys
import json
import time
import logging
import logging.config
# ==============================================================================
import vPlayer

# ==============================================================================
# Global values
_logConfigFile = './config/vLogConfig.json'
_playerConfigFile = './config/vPlayerConfig.json'
# ==============================================================================
if __name__ == "__main__":
    # ======================================
    # load config
    if os.path.exists(_logConfigFile):
        with open(_logConfigFile, "r", encoding='utf-8') as logf:
            logging.config.dictConfig(json.load(logf))
    else:
        logging.error('vLogConfig.json donot exist')
    if os.path.exists(_playerConfigFile):
        with open(_playerConfigFile, 'r', encoding='utf-8') as confList:
            vPlayer._GENV['ConfigDict'] = json.load(confList)
    else:
        logging.error('vPlayerConfig.json donot exist')
    # ======================================
    logging.info('vMain Running')
    xPlayer = vPlayer.vPlayer('10.0.0.15','9527','10.0.0.15','7408')
    xPlayer.run()
    time.sleep(500)
    xPlayer.stop()
