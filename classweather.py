import asyncio
import aiohttp
import os
import re
from datetime import datetime, timedelta, time
from aiohttp.web import RouteTableDef, run_app, Application, Request, Response, FileResponse, json_response

# Define routing table
routes = RouteTableDef()

weather_cache = {}

@routes.get('/')
async def serve_index(request: Request) -> FileResponse:
    return FileResponse("index.html")

@routes.post('/weather')
async def POST_weather(request: Request) -> Response:
    request_data = await request.json()
    course_name = request_data["course"]

    normalized_course_id = normalize_course_id(course_name)
    formatted_id = format_course_id(normalized_course_id)

    course_schedule = await retrieve_course_schedule(normalized_course_id)
    if not course_schedule:
        return json_response({"error": "Course not found"}, status=400)

    next_class_date, start_time = parse_next_meeting(course_schedule["Start Time"], course_schedule["Days of Week"])
    next_class_datetime = datetime.combine(next_class_date, start_time)
    forecast_time = next_class_datetime.replace(minute=0, second=0, microsecond=0)
    cache_key = f"{normalized_course_id}_{next_class_datetime.strftime('%Y-%m-%d_%H:%M:%S')}"

    time_gap = forecast_time - datetime.now()
    if time_gap.total_seconds() > 144 * 60 * 60:
        response_payload = {
            "course": formatted_id,
            "nextCourseMeeting": next_class_datetime.strftime('%Y-%m-%d %H:%M:%S'),
            "forecastTime": forecast_time.strftime('%Y-%m-%d %H:%M:%S'),
            "temperature": "forecast unavailable",
            "shortForecast": "forecast unavailable"
        }
        store_forecast(cache_key, response_payload)
        return json_response(response_payload)

    forecast_info = await obtain_forecast_data(normalized_course_id, forecast_time)
    if forecast_info:
        temperature, weather_description = extract_forecast_details(forecast_info, forecast_time)
        response_payload = {
            "course": formatted_id,
            "nextCourseMeeting": next_class_datetime.strftime('%Y-%m-%d %H:%M:%S'),
            "forecastTime": forecast_time.strftime('%Y-%m-%d %H:%M:%S'),
            "temperature": temperature,
            "shortForecast": weather_description
        }
        store_forecast(cache_key, response_payload)
        return json_response(response_payload)
    else:
        return json_response({"error": "Could not retrieve weather forecast"}, status=500)

@routes.get('/weatherCache')
async def get_cached_weather(request: Request) -> Response:
    if not weather_cache:
        return json_response({})
    return json_response(weather_cache)


# mine
def parse_next_meeting(start_time_str, meeting_days_str):
    scheduled_time = datetime.strptime(start_time_str, "%I:%M %p").time()
    days_map = {'M': 0, 'T': 1, 'W': 2, 'R': 3, 'F': 4, 'S': 5, 'U': 6}
    today = datetime.now().weekday()
    meeting_dates = []
    for day_char in meeting_days_str:
        day_offset = (days_map[day_char] - today) % 7
        meeting_date = datetime.now() + timedelta(days=day_offset)
        if day_offset == 0 and datetime.now().time() >= scheduled_time:
            meeting_date += timedelta(days=7)
        meeting_dates.append(meeting_date.date())
    return min(meeting_dates), scheduled_time

def normalize_course_id(course_identifier):
    cleaned_id = course_identifier.replace(" ", "").lower()
    return cleaned_id.upper()

def format_course_id(course_identifier):
    match = re.match(r'([a-zA-Z]+)(\d+)', course_identifier)
    if not match:
        return None
    dept_code, course_num = match.groups()
    return f"{dept_code.upper()} {course_num}"

async def retrieve_course_schedule(course_identifier):
    course_service_url = os.getenv('COURSES_MICROSERVICE_URL')
    match = re.match(r'([a-zA-Z]+)(\d+)', course_identifier)
    if not match:
        return None
    dept_code, course_num = match.groups()
    course_api_url = f"{course_service_url}/{dept_code.upper()}/{course_num}/"
    async with aiohttp.ClientSession() as session:
        async with session.get(course_api_url) as response:
            return await response.json() if response.status == 200 else None

async def retrieve_forecast_url(lat, long):
    point_api_url = f"https://api.weather.gov/points/{lat},{long}"
    async with aiohttp.ClientSession() as session:
        async with session.get(point_api_url, headers={"User-Agent": "WeatherApp"}) as response:
            return (await response.json())['properties']['forecastHourly']

async def request_weather_forecast(forecast_url):
    async with aiohttp.ClientSession() as session:
        async with session.get(forecast_url, headers={"User-Agent": "WeatherApp"}) as response:
            return await response.json()

def store_forecast(course_key, forecast_info):
    weather_cache[course_key] = forecast_info

def fetch_cached_forecast(course_key):
    return weather_cache.get(course_key, None)

async def obtain_forecast_data(course_id, meeting_time):
    cache_identifier = f"{course_id}_{meeting_time.strftime('%Y-%m-%d_%H:%M')}"
    cached_data = fetch_cached_forecast(cache_identifier)
    if cached_data:
        return cached_data
    lat, long = 40.11, -88.24  
    forecast_api_url = await retrieve_forecast_url(lat, long)
    forecast_data = await request_weather_forecast(forecast_api_url)
    store_forecast(cache_identifier, forecast_data)
    return forecast_data

def extract_forecast_details(forecast_data, meeting_time):
    for period in forecast_data['properties']['periods']:
        period_start = datetime.strptime(period['startTime'], "%Y-%m-%dT%H:%M:%S%z")
        if period_start.date() == meeting_time.date() and period_start.time() == meeting_time.time():
            return period['temperature'], period['shortForecast']
    return None, None

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, default="0.0.0.0")
    parser.add_argument('-p', '--port', type=int, default=5000)
    args = parser.parse_args()

    app = Application()
    app.add_routes(routes)
    run_app(app, host=args.host, port=args.port)
