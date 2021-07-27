"""Support for Naver Weather Sensors."""
import logging
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity

from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_PRECIPITATION,
    ATTR_FORECAST_TEMP,
    ATTR_FORECAST_TEMP_LOW,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
    ATTR_FORECAST_WIND_SPEED,
    PLATFORM_SCHEMA,
    WeatherEntity,
)
from homeassistant.const import (CONF_SCAN_INTERVAL)

REQUIREMENTS = ["beautifulsoup4==4.9.0"]

_LOGGER = logging.getLogger(__name__)

# naver conditions
_CONDITIONS = {
    'ws1'  : ['sunny',        '맑음',        '맑음(낮)'],
    'ws2'  : ['clear-night',  '맑음 (밤)',   '맑음(밤)'],
    'ws3'  : ['partlycloudy', '대체로 흐림', '구름조금(낮)'],
    'ws4'  : ['partlycloudy', '대체로 흐림', '구름조금(밤)'],
    'ws5'  : ['partlycloudy', '대체로 흐림', '구름많음(낮)'],
    'ws6'  : ['partlycloudy', '대체로 흐림', '구름많음(밤)'],
    'ws7'  : ['cloudy',       '흐림',        '흐림'],
    'ws8'  : ['rainy',        '비',          '약한비'],
    'ws9'  : ['rainy',        '비',          '비'],
    'ws10' : ['pouring',      '호우',        '강한비'],
    'ws11' : ['snowy',        '눈',          '약한눈'],
    'ws12' : ['snowy',        '눈',          '눈'],
    'ws13' : ['snowy',        '눈',          '강한눈'],
    'ws14' : ['snowy',        '눈',          '진눈깨비'],
    'ws15' : ['rainy',        '비',          '소나기'],
    'ws16' : ['snowy-rainy',  '진눈개비',    '소낙 눈'],
    'ws17' : ['fog',          '안개',        '안개'],
    'ws18' : ['lightning',    '번개',        '번개,뇌우'],
    'ws19' : ['snowy',        '눈',          '우박'],
    'ws20' : ['fog',          '안개',        '황사'],
    'ws21' : ['snowy-rainy',  '진눈개비',    '비 또는 눈'],
    'ws22' : ['rainy',        '비',          '가끔 비'],
    'ws23' : ['snowy',        '눈',          '가끔 눈'],
    'ws24' : ['snowy-rainy',  '진눈개비',    '가끔 비 또는 눈'],
    'ws25' : ['partlycloudy', '대체로 흐림', '흐린 후 갬'],
    'ws26' : ['partlycloudy', '대체로 흐림', '뇌우 후 갬'],
    'ws27' : ['partlycloudy', '대체로 흐림', '비 후 갬'],
    'ws28' : ['partlycloudy', '대체로 흐림', '눈 후 갬'],
    'ws29' : ['rainy',        '비',          '흐려져 비'],
    'ws30' : ['snowy',        '눈',          '흐려져 눈']
}

# naver provide infomation
_INFO = {
    'Location':             ['네이버 날씨 - 위치',           '',      'hass:map-marker-radius'],
    'Weather_Condition':    ['네이버 날씨 - 현재 날씨',       '',      'hass:weather-cloudy'],
    'Current_Temperature':  ['네이버 날씨 - 현재 온도',       '°C',    'hass:thermometer'],
    'Low_Temperature':      ['네이버 날씨 - 최저 온도',       '°C',    'hass:thermometer-chevron-down'],
    'High_Temperature':     ['네이버 날씨 - 최고 온도',       '°C',    'hass:thermometer-chevron-up'],
    'Apparent_Temperature': ['네이버 날씨 - 체감 온도',       '°C',    'hass:thermometer'],
    'Humidity':             ['네이버 날씨 - 현재 습도',       '%',     'hass:water-percent'],
    'Wind_Speed':           ['네이버 날씨 - 현재 풍속',       'm/s',   'hass:weather-windy'],
    'Wind_Direction':       ['네이버 날씨 - 현재 풍향',       '',      'hass:weather-windy'],
    'Precipitation':        ['네이버 날씨 - 시간당 강수량',    'mm',    'hass:weather-pouring'],
    'Ultraviolet_Index':    ['네이버 날씨 - 자외선 지수',      '',      'hass:weather-sunny-alert'],
    'Ultraviolet_Grade':    ['네이버 날씨 - 자외선 수준',      '',      'hass:weather-sunny-alert'],
    'Ozon':                 ['네이버 날씨 - 오존',           'ppm',   'hass:alpha-o-circle'],
    'Ozon_Level':           ['네이버 날씨 - 오존 수준',       '',      'hass:alpha-o-circle'],
    'Fine_Dust':            ['네이버 날씨 - 미세먼지',        'μg/m³', 'hass:blur'],
    'Fine_Dust_Level':      ['네이버 날씨 - 미세먼지 수준',    '',      'hass:blur'],
    'Ultrafine_Dust':       ['네이버 날씨 - 초미세먼지',      'μg/m³',  'hass:blur-linear'],
    'Ultrafine_Dust_Level': ['네이버 날씨 - 초미세먼지 수준',  '',       'hass:blur-linear'],
    'Tomorrow_Morning_Temperature':         ['네이버 날씨 - 내일 최저 온도', '°C', 'hass:thermometer-chevron-down'],
    'Tomorrow_Morning_Weather_Condition':   ['네이버 날씨 - 내일 오전 날씨', '',   'hass:weather-cloudy'],
    'Tomorrow_Afternoon_Temperature':       ['네이버 날씨 - 내일 최고 온도', '°C', 'hass:thermometer-chevron-up'],
    'Tomorrow_Afternoon_Weather_Condition': ['네이버 날씨 - 내일 오후 날씨', '',   'hass:weather-cloudy']
}

# area
CONF_AREA    = 'area'
DEFAULT_AREA = '날씨'

SCAN_INTERVAL = timedelta(seconds=3)

_UPDATE_CALL_COUNT_MAIN = 0
_UPDATE_CALL_COUNT_SUB = 0

# area_sub
CONF_AREA_SUB    = 'area_sub'
DEFAULT_AREA_SUB = ''

CONF_SCAN_INTERVAL_SUB = 'scan_interval_sub'
SCAN_INTERVAL_SUB = timedelta(seconds=1020)

# sensor 사용여부
CONF_SENSOR_USE = 'sensor_use'
DEFAULT_SENSOR_USE = 'N'

BSE_URL = 'https://search.naver.com/search.naver?query={}'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_AREA, default=DEFAULT_AREA): cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=SCAN_INTERVAL): cv.time_period,
    vol.Optional(CONF_AREA_SUB, default=DEFAULT_AREA_SUB): cv.string,
    vol.Optional(CONF_SCAN_INTERVAL_SUB, default=SCAN_INTERVAL_SUB): cv.time_period,
    vol.Optional(CONF_SENSOR_USE, default=DEFAULT_SENSOR_USE): cv.string,
})


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Demo weather."""
    # sensor use
    sensor_use    = config.get(CONF_SENSOR_USE)

    # area config
    area          = config.get(CONF_AREA)
    SCAN_INTERVAL = config.get(CONF_SCAN_INTERVAL)

    #API
    api = NWeatherAPI(area)

    api.update()

    rslt = api.result
    cur  = api.forecast

    # sensor add
    if sensor_use == 'Y':
        sensors = []
        child   = []

        for key, value in api._sensor.items():
            sensor = childSensor('multiple_attributes_naver_weather', key, value, 'M')
            child   += [sensor]
            sensors += [sensor]

        sensors += [NWeatherSensor('multiple_attributes_naver_weather', api, child, 'M')]

        add_entities(sensors, True)

    add_entities([NaverWeather(cur, api, 'M')])

    #sub
    area_sub = config.get(CONF_AREA_SUB)
    SCAN_INTERVAL_SUB = config.get(CONF_SCAN_INTERVAL)

    if (len(area_sub) > 0):
        sub = NWeatherAPI(area_sub)
        sub.update()

        rslt_sub = sub.result
        cur_sub  = sub.forecast

        add_entities([NaverWeather(cur_sub, sub, 'S')])


class NWeatherAPI:
    """NWeather API."""

    def __init__(self, area):
        """Initialize the NWeather API.."""
        self.area     = area
        self.result   = {}
        self.forecast = []

        self._sensor  = {}

    def update(self):
        """Update function for updating api information."""
        try:
            url = BSE_URL.format(self.area)

            hdr = {'User-Agent': ('mozilla/5.0 (windows nt 10.0; win64; x64) applewebkit/537.36 (khtml, like gecko) chrome/78.0.3904.70 safari/537.36')}

            response = requests.get(url, headers=hdr, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            Temperature = ""
            CheckDust = []

            # 지역
            Location = soup.find('span', {'class':'btn_select'}).text

            # 현재 온도
            Current_Temperature = soup.find('span', {'class': 'todaytemp'}).text

            # 현재 날씨
            Weather_Condition = soup.find('p', {'class' : 'cast_txt'}).text

            # 오늘 최저 온도, 최고 온도, 체감 온도
            Low_Temperature      = soup.find('span', {'class' : 'min'}).select('span.num')[0].text
            High_Temperature     = soup.find('span', {'class' : 'max'}).select('span.num')[0].text
            Apparent_Temperature = soup.find('span', {'class' : 'sensible'}).select('em > span.num')[0].text

            # 시간당 강수량
            TodayPrecipitation = soup.find('span', {'class' : 'rainfall'})
            Precipitation = '-'

            if TodayPrecipitation is not None:
                TodayPrecipitationSelect = TodayPrecipitation.select('em > span.num')

                for rain in TodayPrecipitationSelect:
                    Precipitation = rain.text

            # today_area
            today_area = soup.find("div", {"class": "today_area _mainTabContent"})

            # today_area > indicator
            indicator = today_area.find("span", {"class": "indicator"})

            # 자외선 지수
            Ultraviolet_Index = "-"

            try:
                if indicator is not None:
                    Ultraviolet_Index_Select = indicator.select("span > span.num")

                    for uv in Ultraviolet_Index_Select:
                        Ultraviolet_Index = uv.text
            except Exception as ex:
                Ultraviolet_Index = 'Error'
                _LOGGER.error("Failed to update NWeather API UltravioletIndex Error : %s", ex )


            # 자외선 등급
            Ultraviolet_Grade = "-"

            try:
                if indicator is not None:
                    Ultraviolet_Grade_Select = indicator.select("span")

                    Ultraviolet_Grade = Ultraviolet_Grade_Select[0].text.replace(Ultraviolet_Index, "")
            except Exception as ex:
                Ultraviolet_Grade = 'Error'
                _LOGGER.error("Failed to update NWeather API UltravioletGrade Error : %s", ex )

            # 미세먼지, 초미세먼지, 오존 수준
            CheckDust1 = soup.find('div', {'class': 'sub_info'})
            CheckDust2 = CheckDust1.find('div', {'class': 'detail_box'})

            for i in CheckDust2.select('dd'):
                CheckDust.append(i.text)

            Fine_Dust = '-'
            Fine_Dust_Level = '-'
            Ultrafine_Dust = '-'
            Ultrafine_Dust_Level = '-'

            try:
                Fine_Dust = CheckDust[0].split('㎍/㎥')[0]
            except Exception as ex:
                Fine_Dust = 'Error'
                _LOGGER.error("Failed to update NWeather API FineDust Error : %s", ex )

            try:
                Fine_Dust_Level = CheckDust[0].split('㎍/㎥')[1]
            except Exception as ex:
                Fine_Dust_Level = 'Error'
                _LOGGER.error("Failed to update NWeather API FineDustLevel Error : %s", ex )

            try:
                Ultrafine_Dust = CheckDust[1].split('㎍/㎥')[0]
            except Exception as ex:
                Ultrafine_Dust = 'Error'
                _LOGGER.error("Failed to update NWeather API UtrafineDust Error : %s", ex )

            try:
                Ultrafine_Dust_Level = CheckDust[1].split('㎍/㎥')[1]
            except Exception as ex:
                Ultrafine_Dust_Level = 'Error'
                _LOGGER.error("Failed to update NWeather API UtrafineDustLevel Error : %s", ex )

            # 오존
            Ozon = '-'
            Ozon_Level = '-'

            try:
                Ozon = CheckDust[2].split("ppm")[0]
            except Exception as ex:
                Ozon = 'Error'
                _LOGGER.error("Failed to update NWeather API Ozon Error : %s", ex )

            #오존등급
            try:
                Ozon_Level = CheckDust[2].split("ppm")[1]
            except Exception as ex:
                Ozon_Level = 'Error'
                _LOGGER.error("Failed to update NWeather API OzonLevel Error : %s", ex )

            # condition
            today_area = soup.find('div', {'class' : 'today_area _mainTabContent'})

            condition_main = today_area.select('div.main_info > span.ico_state')[0]["class"][1]
            condition      = _CONDITIONS[condition_main][0]

            # 현재 습도
            humi_tab = soup.find('div', {'class': 'info_list humidity _tabContent _center'})
            Humidity = humi_tab.select('ul > li.on.now > dl > dd.weather_item._dotWrapper > span')[0].text

            # 현재 풍속
            wind_tab       = soup.find('div', {'class': 'info_list wind _tabContent _center'})
            Wind_Speed     = wind_tab.select('ul > li.on.now > dl > dd.weather_item._dotWrapper > span')[0].text
            Wind_Direction = wind_tab.select('ul > li.on.now > dl > dd.item_condition > span.wt_status')[0].text.strip()

            # 내일 오전, 오후 온도 및 날씨 확인
            tomorrowArea  = soup.find('div', {'class': 'tomorrow_area'})
            tomorrowCheck = tomorrowArea.find_all('div', {'class': 'main_info morning_box'})

            # 내일 오전 온도
            Tomorrow_Morning_Temperature = tomorrowCheck[0].find('span', {'class': 'todaytemp'}).text

            # 내일 오전 날씨
            Tomorrow_Morning_Weather_Condition_1 = tomorrowCheck[0].find('div', {'class' : 'info_data'})
            Tomorrow_Morning_Weather_Condition_2 = Tomorrow_Morning_Weather_Condition_1.find('ul', {'class' : 'info_list'})
            Tomorrow_Morning_Weather_Condition   = Tomorrow_Morning_Weather_Condition_2.find('p', {'class' : 'cast_txt'}).text

            # 내일 오후 온도
            Tomorrow_Afternoon_Temperature_1 = tomorrowCheck[1].find('p', {'class' : 'info_temperature'})
            Tomorrow_Afternoon_Temperature   = Tomorrow_Afternoon_Temperature_1.find('span', {'class' : 'todaytemp'}).text

            # 내일 오후 날씨
            Tomorrow_Afternoon_Weather_Condition_1 = tomorrowCheck[1].find('div', {'class' : 'info_data'})
            Tomorrow_Afternoon_Weather_Condition_2 = Tomorrow_Afternoon_Weather_Condition_1.find('ul', {'class' : 'info_list'})
            Tomorrow_Afternoon_Weather_Condition   = Tomorrow_Afternoon_Weather_Condition_2.find('p', {'class' : 'cast_txt'}).text

            #주간날씨
            weekly = soup.find('div', {'class': 'table_info weekly _weeklyWeather'})

            date_info = weekly.find_all('li', {'class': 'date_info today'})

            forecast = []

            reftime = datetime.now()

            for di in date_info:
                data = {}

                #day
                day = di.select('span.day_info')

                dayInfo = ""

                for t in day:
                    dayInfo = t.text.strip()
                    #data['datetime'] = dayInfo

                data['datetime'] = reftime

                #temp
                temp = di.select('dl > dd > span')
                temptext = ''

                for t in temp:
                    temptext += t.text

                arrTemp = temptext.split('/')

                data['templow']     = float(arrTemp[0])
                data['temperature'] = float(arrTemp[1])

                #condition
                condition_am = di.select('span.point_time.morning > span.ico_state2')[0]
                condition_pm = di.select('span.point_time.afternoon > span.ico_state2')[0]

                data['condition']    = _CONDITIONS[condition_pm["class"][1]][0]
                data['condition_am'] = _CONDITIONS[condition_am["class"][1]][2]
                data['condition_pm'] = _CONDITIONS[condition_pm["class"][1]][2]

                #rain_rate
                rain_m = di.select('span.point_time.morning > span.rain_rate > span.num')
                for t in rain_m:
                    data['rain_rate_am'] = int(t.text)

                rain_a = di.select('span.point_time.afternoon > span.rain_rate > span.num')
                for t in rain_a:
                    data['rain_rate_pm'] = int(t.text)

                if ( dayInfo.split(' ')[1] != "오늘" ):
                    forecast.append(data)

                reftime = reftime + timedelta(days=1)

            self.forecast = forecast

            #날씨
            weather = dict()
            weather["Location"]          = Location
            weather["Temperature"]       = Current_Temperature
            weather["Humidity"]          = Humidity
            weather["Condition"]         = condition
            weather["Weather_Condition"] = Weather_Condition
            weather["Wind_Speed"]        = Wind_Speed
            weather["Wind_Direction"]    = Wind_Direction

            self.result = weather

            #sensor
            ws = dict()
            ws["Location"]             = Location
            ws["Weather_Condition"]    = Weather_Condition
            ws["Current_Temperature"]  = Current_Temperature
            ws["Low_Temperature"]      = Low_Temperature
            ws["High_Temperature"]     = High_Temperature
            ws["Apparent_Temperature"] = Apparent_Temperature
            ws["Humidity"]             = Humidity
            ws["Wind_Speed"]           = Wind_Speed
            ws["Wind_Direction"]       = Wind_Direction
            ws['Precipitation']        = Precipitation
            ws["Ultraviolet_Index"]    = Ultraviolet_Index
            ws["Ultraviolet_Grade"]    = Ultraviolet_Grade
            ws["Ozon"]                 = Ozon
            ws["Ozon_Level"]           = Ozon_Level
            ws["Fine_Dust"]            = Fine_Dust
            ws["Fine_Dust_Level"]      = Fine_Dust_Level
            ws["Ultrafine_Dust"]       = Ultrafine_Dust
            ws["Ultrafine_Dust_Level"] = Ultrafine_Dust_Level
            ws["Tomorrow_Morning_Temperature"]         = Tomorrow_Morning_Temperature
            ws["Tomorrow_Morning_Weather_Condition"]   = Tomorrow_Morning_Weather_Condition
            ws["Tomorrow_Afternoon_Temperature"]       = Tomorrow_Afternoon_Temperature
            ws["Tomorrow_Afternoon_Weather_Condition"] = Tomorrow_Afternoon_Weather_Condition

            self._sensor = ws

        except Exception as ex:
            _LOGGER.error('Failed to update NWeather API status Error: %s', ex)
            raise


class NaverWeather(WeatherEntity):
    """Representation of a weather condition."""

    def __init__(self, forecast, api, gb):
        """Initialize the Naver Weather."""
        self._icon             = 'hass:weather-partly-cloudy'
        self._name             = '네이버 날씨'
        self._entity_id        = "weather.naver_weather"
        self._condition        = api.result["Temperature"]
        self._temperature      = float(api.result["Temperature"])
        self._temperature_unit = '°C'
        self._humidity         = int(api.result["Humidity"])
        self._wind_speed       = (float(api.result["Wind_Speed"]) * 3.6)
        self._forecast         = forecast
        self._api              = api
        self._gb               = gb

    def update(self):
        """Update current conditions."""
        global _UPDATE_CALL_COUNT_MAIN

        _UPDATE_CALL_COUNT_MAIN += 1

        if _UPDATE_CALL_COUNT_MAIN < 100:  # 3 x 100 = Runs every 300 seconds.
            return
        else:
            _UPDATE_CALL_COUNT_MAIN = 0

        self._api.update()

        self._forecast = self._api.forecast

        if not self._forecast:
            _LOGGER.info("Don't receive weather data from NAVER!")

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return self._icon

    @property
    def name(self):
        """Return the name of the sensor."""
        if self._gb == 'M':
            return '{}'.format(self._name)
        else:
            return '{}_sub'.format(self._name)

    @property
    def entity_id(self):
        """Return the entity ID for this entity."""
        return self._entity_id

    @property
    def temperature(self):
        """Return the temperature."""
        return float(self._api.result["Temperature"])

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._temperature_unit

    @property
    def humidity(self):
        """Return the humidity."""
        return int(self._api.result["Humidity"])

    @property
    def wind_speed(self):
        """Return the wind speed."""
        return (float(self._api.result["Wind_Speed"]) * 3.6)

    @property
    def wind_bearing(self):
        """Return the wind bearing."""
        return self._api.result["Wind_Direction"]

    @property
    def condition(self):
        """Return the weather condition."""
        return self._api.result["Condition"]

    @property
    def state(self):
        """Return the weather state."""
        return self._api.result["Condition"]

    @property
    def attribution(self):
        """Return the attribution."""
        return ''

    @property
    def forecast(self):
        """Return the forecast."""
        return self._forecast


class childSensor(Entity):
    """Representation of a NWeather Sensor."""
    _STATE = None

    def __init__(self, name, key, value, gb):
        """Initialize the NWeather sensor."""
        self._name  = name
        self._key   = key
        self._value = value
        self._STATE = value
        self._gb    = gb

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return _INFO[self._key][2]

    @property
    def name(self):
        """Return the name of the sensor."""
        return _INFO[self._key][0]

    @property
    def entity_id(self):
        """Return the entity ID for this entity."""
        if self._gb == 'M':
            return 'sensor.naver_weather_{}'.format(self._key.lower())
        else:
            return 'sensor.naver_weather_sub_{}'.format(self._key.lower())

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._value

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return _INFO[self._key][1]

    def update(self):
        """Get the latest state of the sensor."""
        self._value = self._STATE

    def setValue(self, value):
        self._STATE = value

        self.update()

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "identifiers": {('naver_weather', self.unique_id)},
            'name': 'Naver Weather',
            'manufacturer': 'naver.com',
            'model': 'naver_weather',
            'sw_version': '1.2.1'
        }

    @property
    def device_state_attributes(self):
        """Attributes."""
        data = {}

        data[self._key] = self._value

        return data


class NWeatherSensor(Entity):
    """Representation of a NWeather Sensor."""

    def __init__(self, name, api, child, gb):
        """Initialize the NWeather sensor."""
        self._icon  = 'hass:weather-partly-cloudy'
        self._name  = '[다중 속성] 네이버 날씨'
        self._api   = api
        self._child = child
        self._gb    = gb

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return self._icon

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def entity_id(self):
        """Return the entity ID for this entity."""
        if self._gb == 'M':
            return 'sensor.multiple_attributes_naver_weather'
        else:
            return 'sensor.multiple_attributes_naver_weather_sub'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._api._sensor["Weather_Condition"]

    def update(self):
        """Get the latest state of the sensor."""
        global _UPDATE_CALL_COUNT_SUB

        _UPDATE_CALL_COUNT_SUB += 1

        if _UPDATE_CALL_COUNT_SUB < 100:  # 3 x 100 = Runs every 300 seconds.
            return
        else:
            _UPDATE_CALL_COUNT_SUB = 0

        if self._api is None:
            return

        self._api.update()

        for sensor in self._child:
            sensor.setValue( self._api._sensor[sensor._key] )

    @property
    def device_state_attributes(self):
        """Attributes."""

        data = {}

        for key, value in self._api._sensor.items():
            data[_INFO[key][0]] = '{}{}'.format(value, _INFO[key][1])

        return data

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "identifiers": {('multiple_attributes_naver_weather', 'quality')},
            'name': 'Naver Weather',
            'manufacturer': 'naver.com',
            'model': 'multiple_attributes_naver_weather'
        }
