FROM python:3.12-slim

COPY . /app
WORKDIR /app

RUN pip install --no-cache-dir -e .

CMD ["predikt", "run-autonomous-trader"]
