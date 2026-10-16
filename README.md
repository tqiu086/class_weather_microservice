# Class-weather microservice

- Built a POST /weather microservice by parsing course names in multiple input formats (e.g., "CSCI-1100", "CS 1100", "1100"), integrating with a course meeting time API to extract schedule metadata, and fetching hourly forecasts from the National Weather Service (NWS), eliminating the need for students and faculty to manually check weather conditions before commuting to upcoming classes.
- Implemented a disk-based caching layer keyed by course identifier with configurable TTL, storing weather results locally to short-circuit redundant NWS API calls, preventing IP-based rate-limiting bans while reducing average response latency from ~800ms to under 5ms for cached requests.
- Implemented fallback logic that served cached weather data when the National Weather Service API was unavailable, improving service resilience and reducing dependence on third-party availability.
