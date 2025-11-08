FROM python:3.11-slim

WORKDIR /app

# build deps for one-off protoc run
RUN pip install --no-cache-dir \
        pyjoules==0.5.1 python-snappy==0.7.3 protobuf==6.31.1 grpcio-tools==1.73.1 requests==2.32.4

# --- 1) copy the Prometheus remote-write protobuf -----------------
COPY remote.proto .

# --- 2) compile proto to Python -----------------------------------
# results in remote_pb2.py next to remote.proto
RUN python -m grpc_tools.protoc -I. --python_out=. remote.proto

# --- 3) copy application code -------------------------------------
COPY power_scraper.py remote_write_pusher.py ./

ENV SAMPLING_PERIOD_S=4
ENV BATCH_SIZE=5
ENV REMOTE_WRITE_URL=http://localhost:9090/api/v1/write

CMD ["python", "remote_write_pusher.py"]