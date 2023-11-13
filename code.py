import os
import time
import json
import busio
import board
import neopixel
import ssl
import wifi
import socketpool
import displayio
from adafruit_datetime import datetime
from adafruit_pm25.i2c import PM25_I2C
from adafruit_bme280.basic import Adafruit_BME280_I2C as BME280
from adafruit_scd4x import SCD4X
from adafruit_max1704x import MAX17048
import adafruit_requests

# Choose a unique device ID for your device, e.g. "yourname-co2-temperature"
DEVICE_ID = None

# This controls how often your device sends data to the database
LOOP_TIME_S = 60

# Public/anonymous connection info for our supabase instance
# (Yep, we've just put the access key in plaintext here :o )
SUPABASE_POST_URL = "https://llhfnnvekwquqvhxyhtz.supabase.co/rest/v1/iot"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxsaGZubnZla3dxdXF2aHh5aHR6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE2OTcyMzM3NDUsImV4cCI6MjAxMjgwOTc0NX0.eNxux3E_ZSqkkQV5KGkaKnSVy0EAXrfQVhu-lFrPHx8"

# Prepare to use the internet 💫
wifi.radio.connect(os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD"))
pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())

def initialize_sensors():
    '''Initialize connections to each possible sensor, if connected
    '''
    i2c = busio.I2C(board.SCL, board.SDA)

    try:
        pm25_sensor = PM25_I2C(i2c)
    except RuntimeError:
        pm25_sensor = None

    try:
        co2_sensor = SCD4X(i2c)
        co2_sensor.start_periodic_measurement()
    except RuntimeError:
        co2_sensor = None
    
    try:
        temperature_sensor = BME280(i2c)
    except RuntimeError:
        temperature_sensor = None

    try: 
        battery_sensor = MAX17048(i2c)
    except RuntimeError:
        battery_sensor = None

    return pm25_sensor, co2_sensor, temperature_sensor, battery_sensor

def post_to_db(sensor_data: dict): 
    ''' Store sensor data in our supabase DB '''
    if not DEVICE_ID:
        raise Exception("Please set a unique device id!")

    print("Posting to DB")
    response = requests.post(
        url=SUPABASE_POST_URL,
        headers={
            'apikey': SUPABASE_KEY,
            'Authorization': f'bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal',
        },
        data=json.dumps({
            'device_id': DEVICE_ID,
            'content': sensor_data,
        }),
    )

    # PostgREST only sends response to a POST when something is wrong
    error_details = response.content
    if error_details:
        print('Received response error code', error_details)
        print(response.headers)
        raise Exception(error_details)
    else:
        print('Post complete')


def collect_data(pm25_sensor, co2_sensor, temperature_sensor, battery_sensor):
    ''' Get the latest data from the sensors, display it, and record it in the cloud. '''
    # Python3 kwarg-style dict concatenation syntax doesn't seem to work in CircuitPython,
    # so we have to use mutation and update the dict as we go along
    all_sensor_data = {}

    if pm25_sensor:
        all_air_quality_data = pm25_sensor.read() if pm25_sensor else {}

        # air_quality_data has a whole lot of keys. Let's just pull out the ones we care about
        all_sensor_data.update({
            'pm2.5': all_air_quality_data['pm25 standard'],
            'pm100': all_air_quality_data['pm100 standard'],
        })

    if battery_sensor:
        all_sensor_data.update({
            'battery_v': battery_sensor.cell_voltage,
            'battery_pct': battery_sensor.cell_percent,
        })

    if (co2_sensor and co2_sensor.data_ready):
        all_sensor_data.update({
            'co2_ppm': co2_sensor.CO2,
            'temperature_c': co2_sensor.temperature,
            'humidity_relative': co2_sensor.relative_humidity
        })

    if temperature_sensor:
        all_sensor_data.update({
            # Note: the CO2 sensor also collects temperature. If you have both, we default to the
            # data collected by this dedicated temperature sensor
            'temperature_c': temperature_sensor.temperature
        })

    print(all_sensor_data)
    post_to_db(all_sensor_data)


pm25_sensor, co2_sensor, temperature_sensor, battery_sensor = initialize_sensors()

while True:
    try:
        collect_data(pm25_sensor, co2_sensor, temperature_sensor, battery_sensor)
    except (RuntimeError, OSError) as e:
        # Sometimes this is invalid PM2.5 checksum or timeout
        print(e)
    time.sleep(LOOP_TIME_S)