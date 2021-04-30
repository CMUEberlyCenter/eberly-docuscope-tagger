[![pipeline status](https://gitlab.com/CMU_Sidecar/docuscope-tag/badges/master/pipeline.svg)](https://gitlab.com/CMU_Sidecar/docuscope-tag/commits/master)

DocuScope Tagger Service
========================
A Singularity application for tagging text based on the DocuScope Ity tagger.

## Requirements
1. [Singularity](https://sylabs.io/guides/3.7/admin-guide/)
1. A DocuScope dictionary in `app/dictionaries/default.json.gz`
   This file is the gzip'ed JSON representation of the dictionary generated with
   CMU_Sidecar/docuscope-dictionary-tools/docuscope-rules>

## Usage
1. Build: `singularity build docuscope-tagger.sif docuscope-tagger.def`
1. `./docuscope-tagger.sif --help` to list command line options.
1. To run tagger: `./docuscope-tagger.sif -c --db {uri}`
where {uri} is the uri of the database containing documents to be tagged.

This is meant to work in conjunction with CMU_Sidecar/docuscope-classroom>
which is designed for visualizing and analyzing the results in a classroom
setting.

## Thanks
This was developed as part of the Sidecar project which is supported by
[Carnegie Mellon University](https://www.cmu.edu/)'s
[Simon Initiative](https://www.cmu.edu/simon/) to create writing analysis
tools for both students and instructors.
