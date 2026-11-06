ARG PYTHON_BASE_IMAGE=python:3.10-slim-bookworm
FROM ${PYTHON_BASE_IMAGE}
WORKDIR /app
COPY proxy.py .
USER 65534:65534
CMD ["python", "proxy.py"]
