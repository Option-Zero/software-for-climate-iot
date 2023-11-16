import busio
import board
import os
import time
import json
import microcontroller
import ssl
import wifi
import traceback
import socketpool
from adafruit_datetime import datetime
from adafruit_pm25.i2c import PM25_I2C
from adafruit_bme280.basic import Adafruit_BME280_I2C as BME280
from adafruit_scd30 import SCD30
from adafruit_scd4x import SCD4X
from adafruit_max1704x import MAX17048
import adafruit_requests

DEVICE_ID = os.getenv('DEVICE_ID')
SUPABASE_POST_URL = os.getenv('SUPABASE_POST_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# This controls how often your device sends data to the database
LOOP_TIME_S = 60

# Prepare to use the internet 💫
def setup_wifi():
    # This is inside a function so that we can call it later if we need to reestablish
    # the connection.
    wifi.radio.connect(os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD"))

setup_wifi()
pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())
requests = setup_wifi()

def initialize_sensors():
    '''Initialize connections to each possible sensor, if connected
    '''
    i2c = busio.I2C(board.SCL, board.SDA)

    try:
        air_quality_sensor = PM25_I2C(i2c)
    except RuntimeError:
        print('No PM2.5 air quality sensor found')
        air_quality_sensor = None

    try:
        co2_sensor = SCD4X(i2c)
        co2_sensor.start_periodic_measurement()
    except Exception:
        print('No CO2 sensor found')
        co2_sensor = None

    try:
        temperature_sensor = BME280(i2c)
    except Exception:
        print('No temperature sensor found')
        temperature_sensor = None

    try: 
        battery_sensor = MAX17048(i2c)
    except Exception:
        print('No battery sensor found')
        battery_sensor = None

    return air_quality_sensor, co2_sensor, temperature_sensor, battery_sensor

def post_to_db(sensor_data: dict): 
    ''' Store sensor data in our supabase DB '''
    if not DEVICE_ID:
        raise Exception("Please set a unique device id!")

    print("Posting to DB")
    try:
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
    except socketpool.SocketPool.gaierror as e:
        print(f'ConnectionError: {e}. Restarting networking.')
        setup_wifi()
        # Attempt to store some diagnostic data about this error
        sensor_data.update({
            'network_reset': True,
            'network_stacktrace': traceback.format_exception(e)
        })
        print('Recursively retrying post with saved stacktrace.')
        response = post_to_db(sensor_data)

    # PostgREST only sends response to a POST when something is wrong
    error_details = response.content
    if error_details:
        print('Received response error code', error_details)
        print(response.headers)
        raise Exception(error_details)
    else:
        print('Post complete')


def collect_data(air_quality_sensor, co2_sensor, temperature_sensor, battery_sensor):
    ''' Get the latest data from the sensors, display it, and record it in the cloud. '''
    # Python3 kwarg-style dict concatenation syntax doesn't seem to work in CircuitPython,
    # so we have to use mutation and update the dict as we go along
    all_sensor_data = {}

    if air_quality_sensor:
        # This sensor collects the following data:
        # PM1.0, PM2.5 and PM10.0 concentration in both standard (at sea level) & enviromental units (at ambient pressure)
        # Particulate matter per 0.1L air, categorized into 0.3um, 0.5um, 1.0um, 2.5um, 5.0um and 10um size bins

        # The data is structured as a dictionary with keys of this format:
        # "pmXX standard"   : PMX.X concentration at standard pressure (sea level)
        # "pmXX env"        : PMX.X concentration at ambient pressure
        # "particles XXum"  : Particulate matter of size > X.Xum per 0.1L air
        air_quality_data = air_quality_sensor.read() if air_quality_sensor else {}

        all_sensor_data.update(air_quality_data)

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
            # Note: the CO2 sensor also collects temperature and relative humidity
            # If you have both, we default to the data collected by this temperature sensor
            'temperature_c': temperature_sensor.temperature,
            'humidity_relative': temperature_sensor.relative_humidity,
            'pressure_hpa': temperature_sensor.pressure,
            'altitude_m': temperature_sensor.altitude,
        })

    print(all_sensor_data)
    post_to_db(all_sensor_data)


air_quality_sensor, co2_sensor, temperature_sensor, battery_sensor = initialize_sensors()

while True:
    try:
        collect_data(air_quality_sensor, co2_sensor, temperature_sensor, battery_sensor)
    except (RuntimeError, OSError) as e:
        # Sometimes this is invalid PM2.5 checksum or timeout
        print(f"{type(e)}: {e}")
        if str(e) == 'pystack exhausted':
            # This happens when our recursive retry logic fails.
            print('Unable to recover from an error. Rebooting in 10s.')
            time.sleep(10)
            microcontroller.on_next_reset(microcontroller.RunMode.NORMAL)
            microcontroller.reset()

    time.sleep(LOOP_TIME_S)
