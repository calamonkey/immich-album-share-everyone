FROM python:3.13-alpine
RUN adduser -D -H -u 10001 albumshare
COPY album_share.py /app/album_share.py
USER albumshare
ENV PYTHONUNBUFFERED=1 HEALTH_FILE=/tmp/last-success
# healthy = a sync succeeded within the last 3 intervals
HEALTHCHECK --interval=60s --start-period=60s CMD python -c "import os,time,sys; sys.exit(time.time()-os.path.getmtime(os.environ['HEALTH_FILE']) > 3*int(os.environ.get('INTERVAL_SECONDS','600')))"
ENTRYPOINT ["python", "/app/album_share.py"]
