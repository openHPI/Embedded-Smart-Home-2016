import RPi.GPIO as GPIO
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import spidev
import time
from datetime import datetime
import os
import json

global sensor_display_thread

# HTTPRequestHandler class
class FirstHTTP_RequestHandler(BaseHTTPRequestHandler):

  def do_GET(self):
      self.send_response(200)
      self.send_header('Content-type', 'application/json')
      self.end_headers()

      response = dict()
      response["temp"] = sensor_display_thread.get_temp()
      response["tempout"] = sensor_display_thread.get_temp_out()
      response["humidity"] = sensor_display_thread.get_humidity()
      response["door"] = sensor_display_thread.get_door()

      message = json.dumps(response)

      self.wfile.write(bytes(message, "utf-8"))

      return

class SensorDisplayThread(threading.Thread):
    spi = None;

    temp = 0
    temp_out = 0
    humidity = 0
    door = 0

    # Commands
    LCD_CLEARDISPLAY        = 0x01
    LCD_RETURNHOME          = 0x02
    LCD_ENTRYMODESET        = 0x04
    LCD_DISPLAYCONTROL      = 0x08
    LCD_CURSORSHIFT         = 0x10
    LCD_FUNCTIONSET         = 0x20
    LCD_SETCGRAMADDR        = 0x40
    LCD_SETDDRAMADDR        = 0x80

    # Entry flags
    LCD_ENTRYRIGHT          = 0x00
    LCD_ENTRYLEFT           = 0x02
    LCD_ENTRYSHIFTINCREMENT = 0x01
    LCD_ENTRYSHIFTDECREMENT = 0x00

    # Control flags
    LCD_DISPLAYON           = 0x04
    LCD_DISPLAYOFF          = 0x00
    LCD_CURSORON            = 0x02
    LCD_CURSOROFF           = 0x00
    LCD_BLINKON             = 0x01
    LCD_BLINKOFF            = 0x00

    # Move flags
    LCD_DISPLAYMOVE         = 0x08
    LCD_CURSORMOVE          = 0x00
    LCD_MOVERIGHT           = 0x04
    LCD_MOVELEFT            = 0x00

    # Function set flags
    LCD_8BITMODE            = 0x10
    LCD_4BITMODE            = 0x00
    LCD_2LINE               = 0x08
    LCD_1LINE               = 0x00
    LCD_5x10DOTS            = 0x04
    LCD_5x8DOTS             = 0x00

    LCD_ROW_OFFSETS         = (0x00,0x40,0x14,0x54)

    #GPIO Pins
    lcd_rs        = 25
    lcd_en        = 23
    lcd_d4        = 26
    lcd_d5        = 16
    lcd_d6        = 20
    lcd_d7        = 21
    lcd_backlight = 24

    #Display Settings
    lcd_columns = 16
    lcd_rows    = 2
    
    def __init__(self):
        threading.Thread.__init__(self)

    def get_temp(self):
        return self.temp

    def get_temp_out(self):
        return self.temp_out

    def get_humidity(self):
        return self.humidity

    def get_door(self):
        return self.door

    # Function to read SPI data from MCP3008 chip
    # Channel must be an integer 0-7
    def read_channel(self, channel):
        adc = self.spi.xfer2([1,(8+channel)<<4,0])
        data = ((adc[1]&3) << 8) + adc[2]
        return data

    # Function to convert data to voltage level,
    # rounded to specified number of decimal places.
    def convert_volts(self, data, places):#implementit
        volts = (data * 3.3) / float(1023)
        volts = round(volts,places)
        return volts

    def volts_to_celsius(self, volts, places):
        return round((volts * 100) - 273.15, places)

    def volts_to_humidity(self, volts, temp, places):

        if temp <= 22.5:
            humidity = round((volts - 0.128) / 0.0286, places)
        elif temp <= 27.5:
            humidity = round((volts - 0.085) / 0.0294, places)
        else:
            humidity = round((volts - 0.038) / 0.0296, places)

        return humidity

    def initDisplay(self):
        for pin in (self.lcd_rs, self.lcd_en, self.lcd_d4, self.lcd_d5, self.lcd_d6, self.lcd_d7, self.lcd_backlight):
            GPIO.setup(pin, GPIO.OUT)

        # Initialisiere Display
        self.write8(0x33)
        self.write8(0x32)

        self.write8(self.LCD_DISPLAYCONTROL | self.LCD_DISPLAYON | self.LCD_CURSOROFF | self.LCD_BLINKOFF)
        self.write8(self.LCD_FUNCTIONSET | self.LCD_4BITMODE | self.LCD_1LINE | self.LCD_2LINE | self.LCD_5x8DOTS)
        self.write8(self.LCD_ENTRYMODESET | self.LCD_ENTRYLEFT | self.LCD_ENTRYSHIFTDECREMENT)

        self.write8(self.LCD_CLEARDISPLAY)  # Display leeren

        time.sleep(0.5)

    def write8(self, value, char_mode=False):

        #Zu schnnelles Schreiben verhindern
        time.sleep(0.001)

        # Set character / data bit.
        GPIO.output(self.lcd_rs, char_mode)

        # Schreibe mehrwertige 4 Bit.
        GPIO.output(self.lcd_d4, ((value >> 4) & 1) > 0)
        GPIO.output(self.lcd_d5, ((value >> 5) & 1) > 0)
        GPIO.output(self.lcd_d6, ((value >> 6) & 1) > 0)
        GPIO.output(self.lcd_d7, ((value >> 7) & 1) > 0)

        self.pulse_enable()

        # Schreibe niederwertigere  4 Bit.
        GPIO.output(self.lcd_d4, (value        & 1) > 0)
        GPIO.output(self.lcd_d5, ((value >> 1) & 1) > 0)
        GPIO.output(self.lcd_d6, ((value >> 2) & 1) > 0)
        GPIO.output(self.lcd_d7, ((value >> 3) & 1) > 0)

        self.pulse_enable()

    def pulse_enable(self):
        GPIO.output(self.lcd_en, 0)
        time.sleep(0.001)

        GPIO.output(self.lcd_en, 1)
        time.sleep(0.001)

        GPIO.output(self.lcd_en, 0)
        time.sleep(0.001)

    def set_cursor(self, col, row):
        if row > self.lcd_rows:
            row = self.lcd_rows-1
        self.write8(self.LCD_SETDDRAMADDR | (col + self.LCD_ROW_OFFSETS[row]))

    def message(self, text):

        """Schreibe text auf display."""
        line = 0
        print(text)
        for char in text:
            if char == '\n':
                line += 1
                col = 0 if (self.LCD_ENTRYLEFT | self.LCD_ENTRYSHIFTDECREMENT) & self.LCD_ENTRYLEFT > 0 else self.lcd_columns-1
                self.set_cursor(col, line)
            else:
                self.write8(ord(char), True)

    def run(self):

        GPIO.setmode(GPIO.BCM)
        self.initDisplay()

        while True:
            
            #GPIO
            GPIO.setup(12, GPIO.OUT)
             
            # SPI bus
            self.spi = spidev.SpiDev()
            self.spi.open(0,0)


            ### READ SENSOR DATA ###
            # Define sensor channels
            temp_in_channel = 1
            temp_out_channel = 2
            humid_in_channel = 0
             
            # Read the sensor data
            adc_temp_in = self.read_channel(temp_in_channel)
            volts_temp_in = self.convert_volts(adc_temp_in, 4)
            celcius_temp_in = self.volts_to_celsius(volts_temp_in, 1)

            adc_temp_out = self.read_channel(temp_out_channel)
            volts_temp_out = self.convert_volts(adc_temp_out, 4)
            celcius_temp_out = self.volts_to_celsius(volts_temp_out, 1)

            adc_humid_in = self.read_channel(humid_in_channel)
            volts_humid_in = self.convert_volts(adc_humid_in, 4)
            humidity_in = self.volts_to_humidity(volts_humid_in, celcius_temp_in, 1)

            # Save results for json and display
            self.temp = celcius_temp_in
            self.temp_out = celcius_temp_out
            self.humidity = humidity_in
            self.door = GPIO.input(12)

            ### WRITTE INFORMATION ON DISPLAY ###

            # Current Date
            timestamp = datetime.now()
            str_time = timestamp.strftime('%d.%m.%y')

            GPIO.output(self.lcd_backlight, 1)
            self.message(str(int(round(celcius_temp_in))) + chr(223) + 'C  '
                         + str(int(round(humidity_in, 0))) + '%  '
                         + str(int(round(celcius_temp_out))) + chr(223) + 'C\n    '
                         + str_time)

            # Reset coursor position
            self.set_cursor(0, 0)
             
            # Wait before repeating loop
            time.sleep(10)

sensor_display_thread = SensorDisplayThread()
sensor_display_thread.start()

server_address = ('0.0.0.0', 8080)
httpd = HTTPServer(server_address, FirstHTTP_RequestHandler)
print('running server...')
httpd.serve_forever()
