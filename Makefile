.PHONY: start test

start:
	python3 courses_microservice/schedules.py &
	COURSES_MICROSERVICE_URL=http://localhost:34000 python3 classweather.py

test:
	python3 -m pytest
