FROM tiangolo/uvicorn-gunicorn-fastapi:python3.7
COPY requirements.txt /tmp
RUN pip install --upgrade pip && pip install --no-cache-dir --upgrade -r /tmp/requirements.txt
COPY ./app /app
