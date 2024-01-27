FROM python:3.11

RUN mkdir -p /app
WORKDIR /app
ADD config.yaml /app/
RUN git clone https://github.com/heiparta/hw2influxdb.git

RUN pip install -r hw2influxdb/requirements.txt


CMD ["python", "hw2influxdb/src/hw2influxdb/hw2influxdb.py", "config.yaml"]
