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
CMD ["hypercorn", "app.main:app", "--bind", "0.0.0.0:80"]
