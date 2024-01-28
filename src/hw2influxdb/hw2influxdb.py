#!/usr/bin/env python3
import argparse
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

class AppArgs(BaseModel):
    config_file: str
    dry_run: bool = False

class InfluxDBConfig(BaseModel):
    host: str
    port = 8086
    database = "energy"
    retention_policy: Optional[str]


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


async def collect_data(
    meter: MeterConfig,
    influx: InfluxDBClient,
    influx_config: InfluxDBConfig,
    dry_run: bool = False,
) -> None:
    # Create session
    timeout = aiohttp.ClientTimeout(total=10)
    session = aiohttp.ClientSession(timeout=timeout, raise_for_status=True)
    # Create url
    url = API_URL.format(host=meter.host)
    # Loop in interval
    while True:
        await asyncio.sleep(meter.interval)

        try:
            # Get data
            data = await get_json(session, url)

            # Parse data as MeterData
            parsed_data = MeterData(**data)
            logging.debug(parsed_data)

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
            if dry_run:
                logging.debug("Send data (dry-run): %s", json_body)
            else:
                influx.write_points(json_body, retention_policy=influx_config.retention_policy)

        except Exception as e:
            logger.exception(e)
            continue


async def run(args: AppArgs) -> None:
    # Read config file
    with open(args.config_file, "r") as f:
        config = yaml.safe_load(f)
    checker_config = CheckerConfig(**config)

    # Connect to influxdb
    influx_config = checker_config.influxdb
    client_params = {
        "host": influx_config.host,
        "port": influx_config.port,
        "database": influx_config.database,
    }
    influx = InfluxDBClient(**client_params)

    # For each meter, start a task to collect data
    tasks = []
    for meter in checker_config.meters:
        tasks.append(collect_data(meter, influx, influx_config, dry_run=args.dry_run))
    await asyncio.gather(*tasks)

def parse_args() -> AppArgs:
    parser = argparse.ArgumentParser(description='Script to collect data and write to InfluxDB.')
    parser.add_argument('config_file', type=str, help='Path to the configuration file.')
    parser.add_argument('--dry-run', action='store_true', help='Run the script in dry run mode.')

    args = parser.parse_args()
    return AppArgs(config_file=args.config_file, dry_run=args.dry_run)


def main() -> None:
    app_args = parse_args()
    asyncio.run(run(app_args))


if __name__ == "__main__":
    main()
