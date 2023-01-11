# Example DocuScope online tagger.

This is an example of a web application that submits text to a DocuScope online
tagger and displays some of the results.  This is intended mostly as a debugging and
demonstration purposes, check out 
[DocuScope Write and Audit](https://github.com/CMUEberlyCenter/eberly-docuscope-wa)
for the production version.

## Required tools

[Node.js](https://nodejs.org/) >= 18.0

## Usage

This works with and is served by the DocuScope tagger service and thus is
accessable through `<deployment>/static/` url, where `<deployment>` is the
uri of the deployed tagger service 
