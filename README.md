[![pipeline status](https://gitlab.com/CMU_Sidecar/docuscope-tag/badges/master/pipeline.svg)](https://gitlab.com/CMU_Sidecar/docuscope-tag/commits/master)

DocuScope Tagger Service
========================
A web api for tagging text based on the DocuScope Ity tagger.

## Requirements
1. [Neo4J](https://neo4j.com/) database.
1. A DocuScope dictionary stored in the Neo4J database generated using
CMU_Sidecar/docuscope-dictionary-tools/docuscope-rules>
1. Optionally [Memcached](https://memcached.org/)
1. Optionally [MySQL](https://www.mysql.com/) database of documents.

## Usage
1. Build docker image: `docker build -t <tag> .`
When deployed, service bound to port 80 of the docker container.
1. Run locally: `pipenv run hypercorn app.main:app --bind 0.0.0.0:8000`

This is meant to work in conjunction with CMU_Sidecar/docuscope-classroom>
which is designed for visualizing and analyzing the results in a classroom
setting.

## Thanks
This was developed as part of the Sidecar project which is supported by
[Carnegie Mellon University](https://www.cmu.edu/)'s
[Simon Initiative](https://www.cmu.edu/simon/) to create writing analysis
tools for both students and instructors.
