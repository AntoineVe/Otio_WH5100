#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
'''
Ce programme récupère les données d'une station météo OTIO WH5100 au moyen
d'un dongle DVB-T de type RTL-2838
'''

__docformat__ = 'restructuredtext en'

from datetime import datetime
import subprocess
import urllib.request
import json
import logging

logging.basicConfig(
        level=logging.DEBUG,
        format='[METEO] - %(asctime)s - %(message)s',
        datefmt='[%d/%m/%Y %H:%M:%S]')

API_URL = "http://127.0.0.1:8088/api/meteo"
RTL_SDR_FREQ = 868304625
'''
Il semble que l'état des piles modifié l'offset de la température
'''
REMPLACEMENT = {
        '6d': '65',
        '6c': '64',
        '6b': '63',
        '6a': '62',
        '25': '65',
        '24': '64',
        '23': '63',
        '22': '62'
        }


def getweather():
    '''
    Lit les données depuis le rtl_sdr
    La fonction pour la température est y = 0.05x-1268.8
    La fonction pour l'humidité est y = x/2
    Pour la vitesse du vent, la formule a était trouvée avec une regression
    linéaire sur une vingtaine de mesure.
    Pour le pluviomètre, il s'agit d'un compteur relatif ; la valeur est
    stockée pour pouvoir effectuer une différence avec la précédente.
    '''

    timestamp = datetime.now().timestamp()

    def temperature(raw):
        return round((0.05*raw-1268.8), 1)

    def humidity(raw):
        return int(round(raw/2))

    def wind(raw):
        return round((0.61264343715451175*raw-0.018142655636458116), 1)

    def rain(raw):
        current = int(raw)
        try:
            with open("/tmp/old_rain", "r") as tmp:
                old_rain = int(tmp.read())
        except FileNotFoundError:
            old_rain = None
        except Exception as err:
            logging.error("Error : " + str(err))
            return int(0)
        if old_rain is None:
            with open("/tmp/old_rain", "w") as tmp:
                tmp.write(str(current))
            return int(0)
        if current > old_rain:
            res = round(float(current-old_rain)*0.3, 1)
            with open("/tmp/old_rain", "w") as tmp:
                tmp.write(str(current))
        else:
            if (current+255)-old_rain < 254:
                res = round(float((current+255)-old_rain)*0.3, 1)
                with open("/tmp/old_rain", "w") as tmp:
                    tmp.write(str(current))
            else:
                res = 0
        return float(res)

    p = subprocess.Popen(
        ["sudo", "rtl_433", "-f", str(RTL_SDR_FREQ), "-q", "-A", "-T", "50"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    try:
        frame = None
        for line in stderr.decode().splitlines():
            if '[00]' in line and '{79}' in line:
                frame = line.split()
                if frame[4] in REMPLACEMENT.keys():
                    frame[4] = REMPLACEMENT[frame[4]]
                t = temperature(int(str(frame[4]) + str(frame[5]), 16))
                h = humidity(int(str(frame[6]), 16))
                w_median = wind(int(frame[7], 16))
                w_gust = wind(int(frame[8], 16))
                r = rain(int(frame[10], 16))
                break
            elif "Time expired" in line:
                logging.error("Aucune donnée reçu !")
                return None
            elif "Signal caught" in line:
                logging.error("Erreur de communication !")
                return None
        if frame:
            with open("/home/antoine/station_meteo.log", "a") as logfile:
                logfile.write(str(frame) + "\n")
            if -20 <= t <= 60 and 0 <= h <= 100 and r <= 10:
                donnees_meteo = {
                    'date': float(timestamp),
                    'temp': float(t),
                    'hum': int(h),
                    'wind': float(w_median),
                    'gust': float(w_gust),
                    'rain': float(r),
                }
                return donnees_meteo, int(frame[10], 16)
            else:
                logging.error("Donnée illogique :/")
                logging.error("T="+str(t)+" H="+str(h)+" R="+str(r))
                logging.error(str(frame))
                return None
        else:
            return None
    except Exception as err:
        logging.error("Impossible de décoder les données : " + str(err))
        for line in stderr.decode().splitlines():
            if '[00]' in line:
                logging.debug(line)
            else:
                logging.debug("Aucunes données valides reçues : « "
                              + line + " »")
        return None


def main():  # pragma: no cover
    ''' Renvoie les données sur une API si exécuté directement '''
    req = urllib.request.Request(API_URL)
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    data = getweather()
    if data is not None:
        logging.info("Données : " + str(data[0]))
        data = json.dumps(data[0]).encode()
        req.add_header('Content-Length', len(data))
        try:
            reponse = urllib.request.urlopen(req, data, 2)
            logging.info("Données envoyées, le serveur a répondu « "
                         + str(reponse.code) + " »")
        except Exception as err:
            logging.error("Aucunes données envoyées : " + str(err))


if __name__ == '__main__':  # pragma: no cover
    while True:
        main()
