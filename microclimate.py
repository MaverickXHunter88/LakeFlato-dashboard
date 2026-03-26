#!/usr/bin/env python3

import colorsys
import sys
import time
import json
import os
from datetime import datetime
import st7735

try:
    # Transitional fix for breaking change in LTR559
    from ltr559 import LTR559
    ltr559 = LTR559()
except ImportError:
    import ltr559

import logging
from subprocess import PIPE, Popen

from bme280 import BME280
from fonts.ttf import RobotoMedium as UserFont
from PIL import Image, ImageDraw, ImageFont
from pms5003 import PMS5003
from pms5003 import ReadTimeoutError as pmsReadTimeoutError
from pms5003 import SerialTimeoutError
from sensirion_i2c_driver import LinuxI2cTransceiver, I2cConnection, CrcCalculator
from sensirion_driver_adapters.i2c_adapter.i2c_channel import I2cChannel
from sensirion_i2c_scd4x.device import Scd4xDevice

from enviroplus import gas

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S")

logging.info("""combined.py - Displays readings from all of Enviro plus' sensors

Press Ctrl+C to exit!

""")
#SCD41 setup
scd_i2c = LinuxI2cTransceiver("/dev/i2c-1")
scd_channel = I2cChannel(
    I2cConnection(scd_i2c),
    slave_address=0x62,
    crc=CrcCalculator(8, 0x31,0xff,0x00)
)
scd41 = Scd4xDevice(scd_channel)

time.sleep(1)

try:
    scd41.start_periodic_measurement()
except Exception as e:
    logging.warning(f"SCD41 start failed (maybe already running):{e}")

time.sleep (5) #allow first measurement

# BME280 temperature/pressure/humidity sensor
bme280 = BME280()

# PMS5003 particulate sensor
pms5003 = PMS5003()
time.sleep(1.0)

# Create ST7735 LCD display class
st7735 = st7735.ST7735(
    port=0,
    cs=1,
    dc="GPIO9",
    backlight="GPIO12",
    rotation=270,
    spi_speed_hz=10000000
)

# Initialize display
st7735.begin()

WIDTH = st7735.width
HEIGHT = st7735.height

# Set up canvas and font
img = Image.new("RGB", (WIDTH, HEIGHT), color=(0, 0, 0))
draw = ImageDraw.Draw(img)
font_size_small = 10
font_size_medium = 14
font_size_large = 20
font = ImageFont.truetype(UserFont, font_size_large)
mediumfont = ImageFont.truetype(UserFont, font_size_medium)
smallfont = ImageFont.truetype(UserFont, font_size_small)
x_offset = 2
y_offset = 2

message = ""

# The position of the top bar
top_pos = 25

# Create a values dict to store the data
variables = ["temperature",
             "pressure",
             "humidity",
             "light",
             "oxidised",
             "reduced",
             "nh3",
             "pm1",
             "pm25",
             "pm10",
             "co2"]

units = ["F",
         "inHg",
         "%",
         "lux",
         "kO",
         "kO",
         "kO",
         "ug/m3",
         "ug/m3",
         "ug/m3",
         "ppm"]

# Define your own warning limits
# The limits definition follows the order of the variables array
# Example limits explanation for temperature:
# [4,18,28,35] means
# [-273.15 .. 4] -> Dangerously Low
# (4 .. 18]      -> Low
# (18 .. 28]     -> Normal
# (28 .. 35]     -> High
# (35 .. MAX]    -> Dangerously High
# DISCLAIMER: The limits provided here are just examples and come
# with NO WARRANTY. The authors of this example code claim
# NO RESPONSIBILITY if reliance on the following values or this
# code in general leads to ANY DAMAGES or DEATH.
limits = [[40, 60, 75, 85],
          [29, 29.6, 30.0, 30.3],
          [20, 30, 60, 70],
          [-1, -1, 30000, 100000],
          [-1, -1, 40, 50],
          [-1, -1, 450, 550],
          [-1, -1, 200, 300],
          [-1, -1, 50, 100],
          [-1, -1, 50, 100],
          [-1, -1, 50, 100],
          [400, 600, 1000, 1500]]

# RGB palette for values on the combined screen
palette = [(0, 0, 255),           # Dangerously Low
           (0, 255, 255),         # Low
           (0, 255, 0),           # Normal
           (255, 255, 0),         # High
           (255, 0, 0)]           # Dangerously High

values = {}

for v in variables:
    values[v] = [1] * WIDTH

#Unit Conversions

def c_to_f(c):
    return (c*9.0/5.0)+32
def hpa_to_inhg(hpa):
    return hpa*0.0295299831


# Displays data and text on the 0.96" LCD
def display_text(variable, data, unit):
    # Maintain length of list
    values[variable] = values[variable][1:] + [data]
    # Scale the values for the variable between 0 and 1
    vmin = min(values[variable])
    vmax = max(values[variable])
    colours = [(v - vmin + 1) / (vmax - vmin + 1) for v in values[variable]]
    # Format the variable name and value
    message = f"{variable[:4]}: {data:.1f} {unit}"
    logging.info(message)
    draw.rectangle((0, 0, WIDTH, HEIGHT), (255, 255, 255))
    for i in range(len(colours)):
        # Convert the values to colours from red to blue
        colour = (1.0 - colours[i]) * 0.6
        r, g, b = [int(x * 255.0) for x in colorsys.hsv_to_rgb(colour, 1.0, 1.0)]
        # Draw a 1-pixel wide rectangle of colour
        draw.rectangle((i, top_pos, i + 1, HEIGHT), (r, g, b))
        # Draw a line graph in black
        line_y = HEIGHT - (top_pos + (colours[i] * (HEIGHT - top_pos))) + top_pos
        draw.rectangle((i, line_y, i + 1, line_y + 1), (0, 0, 0))
    # Write the text at the top in black
    draw.text((0, 0), message, font=font, fill=(0, 0, 0))
    st7735.display(img)


# Saves the data to be used in the graphs later and prints to the log
def save_data(idx, data):
    variable = variables[idx]
    # Maintain length of list
    values[variable] = values[variable][1:] + [data]
    unit = units[idx]
    message = f"{variable[:4]}: {data:.1f} {unit}"
    logging.info(message)

def log_snapshot():
    global last_log_time
    
    now= time.time()
    if now-last_log_time < log_interval:
        return
    try:
        entry ={
            "timestamp": datetime.utcnow().isoformat(),
            "temperature_f": values["temperature"][-1],
            "pressure_inhg": values["pressure"][-1],
            "humidity_pct": values["humidity"][-1],
            "light_lux": values["light"][-1],
            "oxidised_ko": values["oxidised"][-1],
            "reduced_ko": values["reduced"][-1],
            "nh3_ko": values["nh3"][-1],
            "pm1_uhm3": values ["pm1"][-1],
            "pm25_ugm3": values ["pm25"][-1],
            "pm10_ugm3": values ["pm10"][-1],
            "co2_ppm": values ["co2"][-1],
        }
        
        log_date = datetime.utcnow().strftime("%Y-%m-%d")
        log_path = f"/home/designperformancelf/data_log_{log_date}.jsonl"    
        
        with open (log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        
        last_log_time=now
    
    except Exception as e:
        logging.warning(f"log_snapshot failed:{e}")
    
# Displays all the text on the 0.96" LCD
def display_everything():
    draw.rectangle((0, 0, WIDTH, HEIGHT), (0, 0, 0))
    
    #Latest values
    temp_value = values["temperature"][-1]
    humidity_value =  values["humidity"][-1]
    pressure_value = values["pressure"][-1]
    light_value = values["light"][-1]
    pm25_value = values["pm25"][-1]
    co2_value = values["co2"][-1]
    
    #Decide which metric get the large "hero" line
    hero_label="TEMP"
    hero_value= f"{temp_value:.1f}"
    hero_unit = "F"
    hero_color = (0,255,0)
    
    #indoor alert priority
    if co2_value > 1000:
        hero_label = "CO2"
        hero_value = f"{int(co2_value)}"
        hero_unit = "ppm"
        hero_color = (255,0,0)
    elif co2_value > 800:
        hero_label = "CO2"
        hero_value = f"{int(co2_value)}"
        hero_unit = "ppm"
        hero_color = (255,255,0)
    else:
        # Outdoor / general comfor emphasis
        if temp_value >95:
            hero_label = "TEMP"
            hero_value = f"{temp_value:.1f}"
            hero_unit = "F"
            hero_color = (255,0,0)
        elif temp_value > 85:
            hero_label = "TEMP"
            hero_value = f"{temp_value:.1f}"
            hero_unit = "F"
            hero_color = (255,255,0)
    #Big top Line
    label_text = f"{hero_label}:{hero_value}"
    draw.text((2,0), f"{hero_label}:{hero_value}",font=font,fill=hero_color)
    
    #Measure width of big text
    text_width = font.getlength(label_text)
    
    #Offset for unit
    unit_x = 2 + int(text_width) +6
    unit_y = 8
    
    draw.text((unit_x,unit_y), f"{hero_unit}",font=smallfont,fill=hero_color)
    draw.line((0,24,WIDTH,24), fill= (120,120,120),width=2)
    
    #smaller supporting metrics below
    small_items = [
    ("RH", f"{humidity_value:.0f}","%"),
    ("LUX", f"{light_value:.0f}",""),
    ("P",f"{pressure_value:.1f}","inHg"),
    ("PM25",f"{pm25_value:.1f}","ug/m3"),
    ("CO2", f"{co2_value:.0f}","ppm"),
    ("TEMP", f"{temp_value:.1f}","F"),
    ]
    
    small_items = [item for item in small_items if item[0] !=hero_label]
    
    top_y = 32
    left_x = 2
    right_x = WIDTH//2-12
    row_gap = 16
    
    for idx, item in enumerate(small_items):
        label,val,unit=item
        x=left_x if idx <3 else right_x
        y= top_y + (idx % 3)*row_gap
        
        small_label_text = f"{label}:{val}"
        draw.text((x,y),small_label_text,font=mediumfont, fill=(255,255,255))
        if unit:
            small_width = mediumfont.getlength(small_label_text)
            draw.text((x + int(small_width)+2, y + 2), unit, font=smallfont, fill=(180,180,180))
    st7735.display(img)
            
    


# Get the temperature of the CPU for compensation
def get_cpu_temperature():
    process = Popen(["vcgencmd", "measure_temp"], stdout=PIPE, universal_newlines=True)
    output, _error = process.communicate()
    return float(output[output.index("=") + 1:output.rindex("'")])



# globals
mode = 11 #starting mode
last_scd41_read = 0
scd41_interval = 5 #seconds
scd41_data = 0.0
last_log_time = 0
log_interval = 5

def main():
    global mode
    global last_scd41_read, scd41_data

    # Tuning factor for compensation. Decrease this number to adjust the
    # temperature down, and increase to adjust up
    factor = 2.25

    cpu_temps = [get_cpu_temperature()] * 5

    delay = 0.5  # Debounce the proximity tap
    last_page = 0
    
    for v in variables:
        values[v] = [1] * WIDTH
    
    try:
        while True:
            proximity = ltr559.get_proximity()

            # If the proximity crosses the threshold, toggle the mode
            if proximity > 1500 and time.time() - last_page > delay:
                mode += 1
                mode %= (len(variables) + 1)
                last_page = time.time()

            # One mode for each variable
            if mode == 0:
                # variable = "temperature"
                unit = "°F"
                cpu_temp = get_cpu_temperature()
                # Smooth out with some averaging to decrease jitter
                cpu_temps = cpu_temps[1:] + [cpu_temp]
                avg_cpu_temp = sum(cpu_temps) / float(len(cpu_temps))
                
                raw_temp = bme280.get_temperature()
                data = raw_temp - ((avg_cpu_temp - raw_temp) / factor)
                temp_c = raw_temp -((avg_cpu_temp - raw_temp) / factor)
                data = (temp_c * 9/5) + 32
                display_text(variables[mode], data, unit)

            if mode == 1:
                # variable = "pressure"
                unit = "hPa"
                data = bme280.get_pressure()
                unit = "inHg"
                pressure_hpa = bme280.get_pressure()
                data = pressure_hpa * 0.029529983071445
                display_text(variables[mode], data, unit)

            if mode == 2:
                # variable = "humidity"
                unit = "%"
                data = bme280.get_humidity()
                display_text(variables[mode], data, unit)

            if mode == 3:
                # variable = "light"
                unit = "Lux"
                if proximity < 10:
                    data = ltr559.get_lux()
                else:
                    data = 1
                display_text(variables[mode], data, unit)

            if mode == 4:
                # variable = "oxidised"
                unit = "kO"
                data = gas.read_all()
                data = data.oxidising / 1000
                display_text(variables[mode], data, unit)

            if mode == 5:
                # variable = "reduced"
                unit = "kO"
                data = gas.read_all()
                data = data.reducing / 1000
                display_text(variables[mode], data, unit)

            if mode == 6:
                # variable = "nh3"
                unit = "kO"
                data = gas.read_all()
                data = data.nh3 / 1000
                display_text(variables[mode], data, unit)

            if mode == 7:
                # variable = "pm1"
                unit = "ug/m3"
                try:
                    data = pms5003.read()
                except (SerialTimeoutError, pmsReadTimeoutError):
                    logging.warning("Failed to read PMS5003")
                else:
                    data = float(data.pm_ug_per_m3(1.0))
                    display_text(variables[mode], data, unit)

            if mode == 8:
                # variable = "pm25"
                unit = "ug/m3"
                try:
                    data = pms5003.read()
                except (SerialTimeoutError, pmsReadTimeoutError):
                    logging.warning("Failed to read PMS5003")
                else:
                    data = float(data.pm_ug_per_m3(2.5))
                    display_text(variables[mode], data, unit)

            if mode == 9:
                # variable = "pm10"
                unit = "ug/m3"
                try:
                    data = pms5003.read()
                except (SerialTimeoutError, pmsReadTimeoutError):
                    logging.warning("Failed to read PMS5003")
                else:
                    data = float(data.pm_ug_per_m3(10))
                    display_text(variables[mode], data, unit)

            if mode == 10:
                # variable = "co2"
                unit = "ppm"
                now = time.time()
                
                if now - last_scd41_read >= scd41_interval:
                    try:
                        result = scd41.read_measurement()
                        if result is not None:
                            co2, scd_temp_c, scd_rh = result 
                            scd41_data = float(co2.value)
                    except Exception as e:
                        logging.warning (f"SCD41 read failed: {e}")
                    finally:    
                        last_scd41_read = now  
                                                      
                data = scd41_data
                display_text ("co2", data, unit)
            
            if mode == 11:
                # Everything on one screen
                cpu_temp = get_cpu_temperature()
                
                # Smooth out with some averaging to decrease jitter
                cpu_temps = cpu_temps[1:] + [cpu_temp]
                avg_cpu_temp = sum(cpu_temps) / float(len(cpu_temps))
                
                #Temperature
                raw_temp = bme280.get_temperature()
                temp_c = raw_temp - ((avg_cpu_temp - raw_temp)/factor)
                raw_data = (temp_c * 9/5) + 32
                save_data(0, raw_data)
                display_everything()
                #Pressure
                pressure_hpa = bme280.get_pressure()
                raw_data = pressure_hpa * 0.02529983071445
                save_data(1, raw_data)
                display_everything()
                #Humidity
                raw_data = bme280.get_humidity()
                save_data(2, raw_data)
                if proximity < 10:
                    raw_data = ltr559.get_lux()
                else:
                    raw_data = 1
                save_data(3, raw_data)
                display_everything()
                gas_data = gas.read_all()
                save_data(4, gas_data.oxidising / 1000)
                save_data(5, gas_data.reducing / 1000)
                save_data(6, gas_data.nh3 / 1000)
                
                display_everything()
                pms_data = None
                try:
                    pms_data = pms5003.read()
                except (SerialTimeoutError, pmsReadTimeoutError):
                    logging.warning("Failed to read PMS5003")
                else:
                    save_data(7, float(pms_data.pm_ug_per_m3(1.0)))
                    save_data(8, float(pms_data.pm_ug_per_m3(2.5)))
                    save_data(9, float(pms_data.pm_ug_per_m3(10)))
                    display_everything()
                #CO2
                now = time.time()
                if now - last_scd41_read >= scd41_interval:
                    try:
                        result = scd41.read_measurement()
                        if result is not None:
                            co2, scd_temp_c, scd_rh= result
                            scd41_data=float(co2.value)
                    except Exception as e:
                        logging.warning(f"SCD41 read failed:{e}")
                    finally:
                        last_scd41_read=now
                save_data(10, scd41_data)
                display_everything()
                log_snapshot()

    # Exit cleanly
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
