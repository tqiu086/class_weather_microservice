import socket, os, subprocess, signal, time, sys
import pytest
import asyncio
import aiohttp
import classweather
import json

@pytest.fixture(autouse=True, scope='session')
def wrap_sockets():
  microservice = subprocess.Popen([sys.executable, "schedules.py"], cwd="courses_microservice")
  os.environ['COURSES_MICROSERVICE_URL'] = 'http://localhost:34000'
  time.sleep(0.5)
  yield
  microservice.send_signal(signal.Signals.SIGINT)
  time.sleep(0.5)
  microservice.terminate()


iscached = False
cachenotes = []
async def test_cache(aiohttp_client):
  global iscached
  
  app = aiohttp.web.Application()
  app.add_routes(classweather.routes)
  client = await aiohttp_client(app)
  
  try:
    resp = await client.get('/weatherCache')
    cachenotes.append(await resp.json())
  except:
    cachenotes.append(None)
  
  t0 = time.time()
  resp = await client.post('/weather', data=b'{"course":"CS 340"}')
  t1 = time.time()
  assert resp.status == 200
  assert resp.content_type == 'application/json'
  oldval = await resp.json()

  try:
    resp = await client.get('/weatherCache')
    cachenotes.append(await resp.json())
  except:
    cachenotes.append(None)
  cachenotes.append(oldval)

  
  t2 = time.time()
  resp = await client.post('/weather', data=b'{"course":"CS 340"}')
  t3 = time.time()
  assert resp.status == 200
  assert resp.content_type == 'application/json'
  assert oldval == await resp.json(), "Cache should not change result"
  assert t3-t2 < (t1-t0)/10, "Caching should make the second call at least 10× faster than first"


  resp = await client.post('/weather', data=b'{"course":"CS 100"}')
  oldval = await resp.json()
  try:
    resp = await client.get('/weatherCache')
    cachenotes.append(await resp.json())
  except:
    cachenotes.append(None)
  cachenotes.append(oldval)

  resp = await client.post('/weather', data=b'{"course":"CS 421"}')
  oldval = await resp.json()
  try:
    resp = await client.get('/weatherCache')
    cachenotes.append(await resp.json())
  except:
    cachenotes.append(None)
  cachenotes.append(oldval)


  iscached = True

async def test_index(aiohttp_client):
  assert iscached, "Must implement caching to pass any tests"
  
  app = aiohttp.web.Application()
  app.add_routes(classweather.routes)
  client = await aiohttp_client(app)
  
  resp = await client.get('/')
  assert resp.status == 200
  assert resp.content_type == 'text/html'
  assert open('index.html').read() == await resp.text()

async def test_init_cache(aiohttp_client):
  assert iscached, "Must implement caching to pass any tests"

  assert cachenotes[0] in ({},[],""), "cache must initially be empty"

async def test_later_cache(aiohttp_client):
  assert iscached, "Must implement caching to pass any tests"

  assert cachenotes[2].get('shortForecast','') in str(cachenotes[1]), "cache must include past forecasts"

async def test_later_cache_2(aiohttp_client):
  assert iscached, "Must implement caching to pass any tests"

  assert cachenotes[4].get('shortForecast','') in str(cachenotes[3]), "cache must include past forecasts"

async def test_later_cache_3(aiohttp_client):
  assert iscached, "Must implement caching to pass any tests"

  assert cachenotes[6].get('shortForecast','') in str(cachenotes[5]), "cache must include past forecasts"



reformat = ('CS 340','cs233','cS 105','StaT 385', 'stat400')
exist = ('TEST 999','CS 225', 'CS 341', 'CS 421', 'CS 100', 'CS 124', 'CS 173', 'STAT 400','ENG 100','CS 199','ENGL 218')
missing = ('TEST 100', 'CS 342')
keys = reformat + exist + missing
results = {}

async def test_many(aiohttp_client):
  assert iscached, "Must implement caching to pass any tests"
  
  app = aiohttp.web.Application()
  app.add_routes(classweather.routes)
  client = await aiohttp_client(app)

  for s in keys:
    try: results[s] = await (await client.post('/weather', data=json.dumps({"course":s}).encode('UTF-8'))).json()
    except BaseException as ex: results[s] = ex
  assert all(isinstance(v,dict) for v in results.values()), "All requests should return a JSON object"

  async with aiohttp.ClientSession() as session:
    for s in keys:
      try:
        async with session.post('http://fa24-cs340-adm.cs.illinois.edu:3408/check/'+s, data=json.dumps(results.get(s)).encode('utf-8')) as resp:
          results[s] = await resp.json()
      except:
        results[s] = 'Checker not running'


@pytest.mark.parametrize('key', reformat)
async def test_course(key):
  for k in range(10):
    if len(results) == len(set(keys)): break
    await asyncio.sleep(1)
  assert len(results) == len(set(keys)), "Ordering problem with pytest; post on CampusWire"
  data = results.get(key,{'course':False})
  assert isinstance(data, dict), "Checking service is down"
  assert data['course'], "Normalize course name "+repr(key)

@pytest.mark.parametrize('key', reformat+exist)
async def test_meeting_time(key):
  for k in range(10):
    if len(results) == len(set(keys)): break
    await asyncio.sleep(1)
  assert len(results) == len(set(keys)), "Ordering problem with pytest; post on CampusWire"
  data = results.get(key,{'nextCourseMeeting':False})
  assert isinstance(data, dict), "Checking service is down"
  assert data['nextCourseMeeting'], "Course meeting time for "+repr(key)

@pytest.mark.parametrize('key', exist)
async def test_forecast_time(key):
  for k in range(10):
    if len(results) == len(set(keys)): break
    await asyncio.sleep(1)
  assert len(results) == len(set(keys)), "Ordering problem with pytest; post on CampusWire"
  data = results.get(key,{'forecastTime':False})
  assert isinstance(data, dict), "Checking service is down"
  assert data['forecastTime'], "Course forecast time for "+repr(key)

@pytest.mark.parametrize('key', exist)
async def test_forecast(key):
  for k in range(10):
    if len(results) == len(set(keys)): break
    await asyncio.sleep(1)
  assert len(results) == len(set(keys)), "Ordering problem with pytest; post on CampusWire"
  data = results.get(key,{'temperature':False,'shortForecast':False})
  assert isinstance(data, dict), "Checking service is down"
  assert data['temperature'] and data['shortForecast'], "Course forecast for "+repr(key)

