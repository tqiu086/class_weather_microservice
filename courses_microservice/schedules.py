"""
This file pulls from the Course Information System's public API,
as documented at https://courses.illinois.edu/cisdocs/explorer,
with local caching to prevent re-sending the same query many times.
The caching is durable on-disk and is perhaps over-eager:
once a course is queried it's first response is used forever,
even if the schedule is later updated.
To clear the cache for a particular term, remove the .jsonl file
for that term (e.g. `2024fall.jsonl`)
"""

import asyncio
import aiohttp

cache = {}

client = None

def loadcache(year,term):
    """Read an on-disk cache into memory"""
    import os, json
    made = cache.get((year,term), {})
    cache[(year,term)] = made
    if not os.path.exists(f'{year}{term}.jsonl'):
        return
    for line in open(f'{year}{term}.jsonl'):
        data = json.loads(line)
        made[tuple(data['key'])] = data['val']

def addtocache(year, term, subj, num, val):
    """Adds an entry to both on-disk cache and in-memory cache"""
    import json
    cache.setdefault((year, term), {})[(subj,num)] = val
    with open(f'{year}{term}.jsonl', 'a') as out:
        out.write(json.dumps({'key':[subj,num],'val':val}, separators=(',',':'))+'\n')

async def readcis(year, term, subj, num):
    """Queries and parses the XML-encoded CIS microservice"""
    import xml.etree.ElementTree as ET
    global client
    if client is None: client = aiohttp.ClientSession()

    async with client.get(f'http://courses.illinois.edu/cisapp/explorer/schedule/{year}/{term}/{subj}/{num}.xml?mode=cascade') as resp:
        if not resp.ok: return {'error':f'{subj} {num} not found in schedule'}
        root = ET.fromstring(await resp.text())
        ans = {}
        for sect in root.findall('.//detailedSection'):
            num = sect.findall('.//sectionNumber')[0].text
            for meeting in sect.findall('.//meeting'):
                kind = meeting.findall('.//type')[0].attrib['code']
                start, end, days = 'ARRANGED', 'ARRANGED', 'ARRANGED'
                try:
                    start = meeting.findall('.//start')[0].text
                    end = meeting.findall('.//end')[0].text
                    days = meeting.findall('.//daysOfTheWeek')[0].text
                except: pass
                ans[num+'-'+kind] = {'start':start, 'end':end, 'days':days}
        return ans
        

async def get_times(subj, num, term=None, year=None):
    """Given a subject and number, returns its full set of sections and meeting times"""
    import datetime
    today = datetime.date.today()
    if not year: year = today.year
    if not term: term = 'spring' if today.month < 6 else 'summer' if today.month < 8 else 'fall'

    if not isinstance(year, int): return {'error':'Year must be an integer'}
    if not isinstance(num, int): return {'error':'Course number must be an integer'}
    if not isinstance(subj, str): return {'error':'Course subject must be a string'}
    if year > today.year+1: return {'error':'Cannot look that far into the future'}
    if year < 2004: return {'error':'The catalog only goes back to 2004'}
    if term not in ('winter','spring','summer','fall'): return {'error':'Invalid term identifier'}
    if not subj or not all(ord('A') <= ord(char) <= ord('Z') for char in subj): return {'error':'Invalid course subject'}

    if (year, term) not in cache:
        await asyncio.to_thread(loadcache, year, term)
    if (subj, num) in cache[(year,term)]:
        return cache[(year,term)][(subj, num)]
    ans = await readcis(year, term, subj, num)
    await asyncio.to_thread(addtocache, year, term, subj, num, ans)
    return ans

def test_999():
    """This course is always 6 days 22 hours from now"""
    import datetime
    when = datetime.datetime.now() + datetime.timedelta(days=6,hours=22)
    return {
        'course': 'TEST 999',
        'Days of Week': 'MTWRFSU'[when.weekday()],
        'Start Time': when.strftime('%I:00 %p')
    }

import aiohttp.web
routes = aiohttp.web.RouteTableDef()

@routes.get('/{subject}/{number}/')
async def microservice(req):
    """The only web service endpoint in this microservice.
    Returns one of the meeting times for a course, preferring
    lectures to labs with various other tie-breaking rules.
    """
    subj = req.match_info['subject']
    num = req.match_info['number']
    try: num = int(num)
    except: pass
    if (subj,num) == ('TEST',999):
        return aiohttp.web.json_response(test_999())
    result = await get_times(subj, num)
    if 'error' in result:
        result['course'] = f'{subj} {num}'
        return aiohttp.web.json_response(result, status=404)
    best = ('',1000)
    order = ['LEC']+[f'L{n:<2}' for n in range(6)] + ['LCD'] + [f'S{n:<2}' for n in range(30)] + ['LBD', 'LBA', 'DIS', 'OD ', 'OLC', 'ONL', 'OLD']
    for k in result:
        if result[k]['start'] == 'ARRANGED': continue
        try: idx = order.index(k[4:])
        except ValueError: idx = -1
        if idx >= 0 and idx < best[-1]:
            best = (k, idx)
        elif best[-1] == 1000:
            best = (k, 999)
    if best[-1] == 1000:
        return aiohttp.web.json_response({'course':f'{subj} {num}', 'error':'No scheduled meetings found'}, status=404)
    return aiohttp.web.json_response({
        'course':f'{subj} {num}',
        'Days of Week': result[best[0]]['days'].strip(),
        'Start Time': result[best[0]]['start'],
    })



if __name__ == '__main__': 
    import os
    os.chdir(os.path.dirname(__file__))

    app = aiohttp.web.Application()
    app.add_routes(routes)
    aiohttp.web.run_app(app, host='0.0.0.0', port=34000) # this function never returns
    if client is not None:
        asyncio.run(client.close())
