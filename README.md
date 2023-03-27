[![pipeline status](https://gitlab.com/CMU_Sidecar/docuscope-tag/badges/master/pipeline.svg)](https://gitlab.com/CMU_Sidecar/docuscope-tag/commits/master)

DocuScope Tagger Service
========================
A web api for tagging text based on the DocuScope Ity tagger.


## Administration and Support

For any questions regarding overall project or the language model used, please contact <suguru@cmu.edu>

The project code is supported and maintained by the [Eberly Center](https://www.cmu.edu/teaching/) at [Carnegie Mellon University](www.cmu.edu). For help with this fork, project, or service please contact <eberly-assist@andrew.cmu.edu>.


## Requirements
1. [Neo4J](https://neo4j.com/) database.
1. A DocuScope dictionary stored in the Neo4J database generated using
CMU_Sidecar/docuscope-dictionary-tools/docuscope-rules> docuscope-rule-neo4j tool and a DocuScope language model.
1. `common-dict.json` file that specifies a hierarchical organization of clusters. [JSON Schema](https://gitlab.com/CMU_Sidecar/docuscope-classroom/-/blob/master/api/common_dictionary_schema.json)
1. `wordclasses.json` file which is the json version of a DocuScope language model's `_wordclasses.txt` file converted using CMU_Sidecar/docuscope-dictionary-tools/docuscope-rules> docuscope-wordclasses tool.
1. `${DICTIONARY}_tones.json.gz` file which is the compressed json version of a DocuScope `_tones.txt` file converted using CMU_Sidecar/docuscope-dictionary-tools/docuscope-tones> ds-tones tool.
1. [MySQL](https://www.mysql.com/) database for storing CMU_Sidecar/docuscope-classroom> documents and performance measures.
1. Optional: [Memcached](https://memcached.org/)


## Configuration
The following environment variable should be set so that the DocuScope tagger
can access the various required services.  The defaults tend to be reasonable values for a development environment where everything is hosted locally and do not reflect values that should be used in any production environment.

| Variable | Description | Default |
| ---      | ---         | ---     |
| **DICTIONARY** | String used in formulating tag labels and used to load the correct dictionary files. | `default` |
| **DICTIONARY_HOME** | Path to base directory of necessary runtime dictionary files specified above. | `<Application's base directory>/dictionary` |
| **DB_HOST** | Hostname of the MySQL database for storing processed documents. | `127.0.0.1` |
| **DB_PORT** | Port of the MySQL document database. | `3306` |
| **DB_PASSWORD** | Password for accessing the document database. [^docker_secrets] | [^blank] |
| **DB_USER** | Username for accessing the document database. [^docker_secrets] | `docuscope` |
| **MEMCACHED_URL** | Hostname for the optional caching service. | `localhost` |
| **MEMCACHED_PORT** | Port of the caching service. | `11211` |
| **MYSQL_DATABASE** | Identifier for document database. | `docuscope` |
| **NEO4J_DATABASE** | Identifier for dictionary database. | `neo4j` |
| **NEO4J_PASSWORD** | Password for accessing the dictionary database. [^docker_secrets] | [^blank] |
| **NEO4J_USER** | Username for accessing the dictionary database. [^docker_secrets] | `neo4j` |
| **NEO4J_URI** | URI of the dictionary database. | `neo4j://localhost:7687/`[^neo4j_protocol] |

[^docker_secrets]: It is recommended to use [Docker secrets](https://docs.docker.com/engine/swarm/secrets/) to get these values.  The application is able to retrieve values from specified files if the environment variable has the `_FILE` affix added.

[^blank]: Passwords intentionally default to None value for security reasons.

[^neo4j_protocol]: See [Neo4J Python Driver](https://neo4j.com/developer/python/) information for more details on the various valid protocols.


## Usage
1. Build docker image: `docker build -t <tag> .`
When deployed, service bound to port 80 of the docker container.
1. Run locally: `pipenv run hypercorn app.main:app --bind 0.0.0.0:8000`

This is meant to work in conjunction with CMU_Sidecar/docuscope-classroom>
which is designed for visualizing and analyzing the results in a classroom
setting and with [DocuScope Write & Audit](https://github.com/CMUEberlyCenter/eberly-docuscope-wa).


## Acknowledgements

This project was partially funded by the [A.W. Mellon Foundation](https://mellon.org/), [Carnegie Mello University](https://www.cmu.edu/)'s [Simon Initiative](https://www.cmu.edu/simon/) Seed Grant, and the [Berkman Faculty Development Fund](https://www.cmu.edu/proseed/proseed-seed-grants/berkman-faculty-development-fund.html).

---
