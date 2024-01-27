#!/usr/bin/env python3
from typing import Optional
from datetime import datetime, timezone
from influxdb import InfluxDBClient
from pydantic import BaseModel
import sys
import yaml
import aiohttp
import asyncio
import logging

# Setup logging to console
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
# Setup logging to stdout
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.DEBUG)
logger.addHandler(stdout_handler)

API_URL = "http://{host}/api/v1/data"

class InfluxDBConfig(BaseModel):
    host: str
    port = 8086
    database = "energy"

class MeterConfig(BaseModel):
    name: str
    host: str
    interval: int = 10

class CheckerConfig(BaseModel):
    influxdb: InfluxDBConfig
    meters: list[MeterConfig]

class MeterData(BaseModel):
    wifi_strength: int
    total_power_import_kwh: float
    total_power_export_kwh: float
    active_power_w: float
    active_power_l1_w: float
    active_power_l2_w: float
    active_power_l3_w: float

    class Config:
        allow_extra = True


async def get_json(session: aiohttp.ClientSession, url: str) -> dict:
    async with session.get(url) as response:
        return await response.json()

async def collect_data(meter: MeterConfig, influx: InfluxDBClient, stop_after: Optional[int] = None) -> None:
    # Create session
    timeout = aiohttp.ClientTimeout(total=10)
    session = aiohttp.ClientSession(timeout=timeout, raise_for_status=True)
    # Create url
    url = API_URL.format(host=meter.host)
    # Loop in interval
    while True:
        if stop_after is not None:
            if stop_after > 0:
                stop_after -= 1
            if stop_after == 0:
                break
        await asyncio.sleep(meter.interval)

        try:
            # Get data
            data = await get_json(session, url)

            # Parse data as MeterData
            parsed_data = MeterData(**data)

            # Create json body
            json_body = [
                {
                    "measurement": "energy_consumption",
                    "tags": {
                        "meter": meter.name,
                    },
                    "time": datetime.now(timezone.utc).isoformat(),
                    "fields": parsed_data.dict(),
                }
            ]
        
            # Write to influxdb, ignore errors
            influx.write_points(json_body)

        except Exception as e:
            logger.exception(e)
            continue

    await session.close()


async def run() -> None:
    # Read config file
    with open(sys.argv[1], "r") as f:
        config = yaml.safe_load(f)
    checker_config = CheckerConfig(**config)

    # Connect to influxdb
    influx = InfluxDBClient(**checker_config.influxdb.dict())

    # For each meter, start a task to collect data
    tasks = []
    for meter in checker_config.meters:
        tasks.append(collect_data(meter, influx)) 
    await asyncio.gather(*tasks)

    

def main() -> None:
    asyncio.run(run())

if __name__ == "__main__":
    main()
