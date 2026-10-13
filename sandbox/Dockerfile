FROM python:3.12-slim

RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn==0.34.0 numpy==2.2.1 pandas==2.2.3 matplotlib==3.10.0 \
    && useradd --create-home --uid 10001 sandbox

COPY app.py /srv/app.py
WORKDIR /srv
USER sandbox
RUN python -c "import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot"

EXPOSE 8090
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090", "--workers", "2"]
