FROM python:3.11-slim

WORKDIR /app
ENV SAMPLING_PERIOD_S=0.1
ENV BATCH_SIZE=10
ENV REMOTE_WRITE_URL=http://localhost:9090/api/v1/write

# build deps for one-off protoc run
RUN pip install --no-cache-dir \
        pyjoules python-snappy protobuf grpcio-tools requests

# --- 1) copy the Prometheus remote-write protobuf -----------------
COPY remote.proto .

# --- 2) compile proto to Python -----------------------------------
# results in remote_pb2.py next to remote.proto
RUN python -m grpc_tools.protoc -I. --python_out=. remote.proto

# --- 3) copy application code -------------------------------------
COPY power_scraper.py remote_write_pusher.py ./

CMD ["python", "remote_write_pusher.py"]