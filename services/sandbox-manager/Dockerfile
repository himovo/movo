ARG PYTHON_BASE_IMAGE=python:3.10-slim-bookworm
FROM ${PYTHON_BASE_IMAGE}

ARG MOVO_PIP_INDEX_URL=
WORKDIR /app
COPY requirements.txt .
RUN if [ -n "${MOVO_PIP_INDEX_URL}" ]; then \
      python -m pip install --no-cache-dir --index-url "${MOVO_PIP_INDEX_URL}" -r requirements.txt; \
    else \
      python -m pip install --no-cache-dir -r requirements.txt; \
    fi
COPY app ./app
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8300"]
