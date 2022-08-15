FROM docker.io/node:latest AS builder
WORKDIR /tmp
COPY ./basic-docuscope-tagger/package*.json /tmp/
RUN npm ci
RUN mkdir -p /basic-docuscope-tagger && cp -a /tmp/node_modules /basic-docuscope-tagger
WORKDIR /basic-docuscope-tagger
COPY ./basic-docuscope-tagger .
RUN npm run build

FROM docker.io/python:latest AS base
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONFAULTHANDLER=1

FROM base AS deps
RUN pip install --upgrade pip
RUN pip install pipenv
COPY ./Pipfile .
COPY ./Pipfile.lock .
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

FROM base AS runtime
ENV PYTHONOPTIMIZE=2
ENV PATH="/.venv/bin:$PATH"
ENV ROOT_PATH=/
RUN useradd --create-home appuser
ARG BRANCH="master"
ARG COMMIT=""
ARG TAG="latest"
ARG USER=""
LABEL branch=${BRANCH}
LABEL commit=${COMMIT}
LABEL maintainer=${USER}
LABEL version=${TAG}
LABEL description="DocuScope Tagger Service"
COPY --from=deps /.venv /.venv
WORKDIR /home/appuser
COPY ./app ./app
COPY --from=builder /basic-docuscope-tagger/dist ./app/static
EXPOSE 80
CMD ["sh", "-c", "hypercorn app.main:app --bind 0.0.0.0:80 --root-path ${ROOT_PATH}"]
