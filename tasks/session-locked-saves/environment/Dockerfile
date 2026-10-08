FROM python:3.12.7-slim-bookworm

# pytest goes in at build time so the verifier never needs the network
RUN pip install --no-cache-dir pytest==8.4.1

WORKDIR /app
COPY app/ /app/
