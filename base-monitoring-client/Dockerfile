FROM python:3.11-slim

WORKDIR /app

# base deps for remote write
RUN pip install --no-cache-dir \
    python-snappy==0.7.3 \
    protobuf==6.31.1 \
    grpcio-tools==1.73.1 \
    requests==2.32.4

# copy proto and generate python file
COPY remote.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. remote.proto

# generic runtime
COPY remote_write_pusher.py monitor_impl.py ./

# sane defaults; can all be overridden from compose/.env
ENV REMOTE_WRITE_URL=http://prometheus:9090/api/v1/write \
    SCRAPE_INTERVAL_S=0.1 \
    PUSH_INTERVAL_S=4 \
    MAX_RETRY_BATCHES=5 \
    RAW_QUEUE_SIZE=1000 \
    PROC_QUEUE_SIZE=1000 \
    LOG_LEVEL=INFO

CMD ["python", "remote_write_pusher.py"]
