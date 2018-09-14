FROM tiangolo/uwsgi-nginx-flask:python3.6-alpine3.7
COPY requirements.txt /tmp
RUN pip install --upgrade pip && pip install --no-cache-dir --upgrade -r /tmp/requirements.txt
COPY ./app /app
