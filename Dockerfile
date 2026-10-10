FROM python:3.12-slim
ARG WITH_BIRDS=0
WORKDIR /app
COPY . .
RUN if [ "$WITH_BIRDS" = "1" ]; then pip install --no-cache-dir birdnet-analyzer; fi
ENV HOST=0.0.0.0 DATA_DIR=/tmp/data
CMD ["python", "server.py"]
