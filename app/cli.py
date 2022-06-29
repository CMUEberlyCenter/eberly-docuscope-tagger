"""Command line interface for DocuScope Tagger.
Run with --help to see options.
"""
import argparse
#import cProfile
import asyncio
import logging
import traceback
import uuid
from collections import Counter
from typing import Optional

import emcache
from neo4j import AsyncGraphDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession,
                                    create_async_engine)
from sqlalchemy.sql.expression import update

from .database import Submission
from .default_settings import SETTINGS, SQLALCHEMY_DATABASE_URI
from .docx_to_text import docx_to_text
from .ds_tagger import get_wordclasses
from .ity.formatters.simple_html_formatter import SimpleHTMLFormatter
from .ity.tagger import ItyTaggerResult, tag_json
from .ity.taggers.docuscope_tagger_neo import DocuscopeTaggerNeo
from .ity.tokenizers.regex_tokenizer import RegexTokenizer
from .ity.tokenizers.tokenizer import TokenType

PARSER = argparse.ArgumentParser(
    prog="docuscope-tagger.sif",
    description="Use DocuScope's Ity tagger to process a document in the database.")
PARSER.add_argument("uuid", nargs='*',
                    help="The id of a document in the DocuScope database.")
# no default in following so as to not reveal password.
#PARSER.add_argument( # from .env
#    "--db",
#    help="URI of the database. <user>:<pass>@<url>:<port>/<database>")
PARSER.add_argument('-c', '--check_db', action='store_true',
                    help="Check the database for any 'pending' documents.")
PARSER.add_argument('-m', '--max_db_documents', type=int, default=-1,
                    help="Maximum number of 'pending' documents to process.")
#PARSER.add_argument('-r', '--rule_db', help="Rule Database URI.") # from .env
#PARSER.add_argument('--memcache', help="Memcache URI.") # from .env
PARSER.add_argument('-v', '--verbose', help="Increase output verbosity.",
                    action="count", default=0)
ARGS = PARSER.parse_args()
LEVELS = [logging.WARNING, logging.INFO, logging.DEBUG]
logging.basicConfig(level=LEVELS[min(len(LEVELS)-1, ARGS.verbose)])

ENGINE: AsyncEngine = create_async_engine(SQLALCHEMY_DATABASE_URI)

DRIVER = AsyncGraphDatabase.driver(
    SETTINGS.neo4j_uri,
    auth=(SETTINGS.neo4j_user,
          SETTINGS.neo4j_password.get_secret_value()))  # pylint: disable=no-member

WORDCLASSES = get_wordclasses()

async def tag(doc_content: str, cache: Optional[emcache.Client]):
    """Construct and run the tagger on the given text."""
    tokenizer = RegexTokenizer()
    tokens = tokenizer.tokenize(doc_content)
    tagger = DocuscopeTaggerNeo(
        return_untagged_tags=False,
        return_no_rules_tags=True,
        return_included_tags=True,
        wordclasses=WORDCLASSES,
        session=DRIVER.session(),
        cache=cache)
    tagger.wordclasses = WORDCLASSES
    rules, tags = await tagger.tag(tokens)
    await tagger.session.close()
    output = SimpleHTMLFormatter().format(
        tags=(rules, tags), tokens=tokens, text_str=doc_content)
    type_count = Counter([token.type for token in tokens])
    not_excluded = set(TokenType) - set(tokenizer.excluded_token_types)
    return tag_json(ItyTaggerResult(
        format_output=output,
        num_excluded_tokens=sum(
            type_count[etype] for etype in tokenizer.excluded_token_types),
        num_included_tokens=sum(type_count[itype]
                                for itype in not_excluded),
        num_punctuation_tokens=type_count[TokenType.PUNCTUATION],
        num_tokens=len(tokens),
        num_word_tokens=type_count[TokenType.WORD],
        tag_chain=[tag.rules[0][0].split(
            '.')[-1] for tag in tagger.tags],
        tag_dict=tagger.rules,
        text_contents=doc_content
    )).dict()

async def tag_entry(doc_id: str, cache: Optional[emcache.Client]):
    """Use DocuScope tagger on the specified document.
    Arguments:
    doc_id: a uuid of the document in the database.
    """
    doc_content = None
    doc_processed = {"ERROR": "No file data to process."}
    doc_state = "error"
    logging.info("Trying to tag %s", doc_id)
    session: AsyncSession
    async with ENGINE.connect() as session:
        subm = await session.execute(select(Submission.content, Submission.name)
                                     .where(Submission.id == doc_id))
        (doc_content, doc_name) = subm.first() or (None, None)
        if doc_content:
            try:
                await session.execute(update(Submission).where(
                    Submission.id == doc_id).values(
                    state="submitted"))
                await session.commit()
            except:
                logging.error("Error while setting status of %s", doc_id)
                await session.rollback()
                raise
    if doc_content:
        try:
            if doc_name.endswith(".docx"):
                doc_content = docx_to_text(doc_content)
            doc_processed = await tag(doc_content, cache)
            if doc_processed.get('ds_num_word_tokens', 0) == 0:
                doc_state = "error"
                doc_processed['error'] = 'Document failed to parse: no word tokens found.'
                logging.error("Invalid parsing results %s", doc_id)
            else:
                doc_state = "tagged"
                logging.info("Successfully tagged %s", doc_id)
        except Exception as exc:  # pylint: disable=W0703
            logging.error("Unsuccessfully tagged %s", doc_id)
            traceback.print_exc()
            doc_processed = {'error': f"{exc}",
                             'trace': traceback.format_exc()}
            doc_state = "error"
    else:
        logging.error("Could not load %s!", doc_id)
        raise FileNotFoundError(doc_id)
    async with ENGINE.connect() as session:
        try:
            await session.execute(update(Submission).where(
                Submission.id == doc_id).values(
                state=doc_state,
                processed=doc_processed))
            await session.commit()
        except:
            logging.error("Error while executing data update for %s", doc_id)
            await session.rollback()
            raise
    logging.info("Finished tagging %s", doc_id)


def valid_uuid(doc_id: str):
    """Check if the given document id is a uuid string."""
    try:
        uuid.UUID(doc_id)
    except ValueError as vexc:
        logging.warning("%s: %s", vexc, doc_id)
        return False
    return True


async def run_tagger(args):
    """Gathers the document ids and runs the tagger on them (multitreaded)"""
    ids = {id for id in args.uuid if valid_uuid(id)}  # only uuids
    async with ENGINE.connect() as session:
        # check if uuids are in database
        results = await session.stream(
            select(Submission.id).where(Submission.id.in_(ids)))
        valid_ids = {str(id) async for (id,) in results}
        check_ids = ids.difference(valid_ids)
        if check_ids:
            logging.warning(
                "Documents do not exist in database: %s", check_ids)
        # If checking the database for 'pending' documents,
        # add all (limit max number) pending documents to list of ids
        if args.check_db:
            query = select(Submission.id).where(Submission.state == 'pending')
            if args.max_db_documents > 0:
                query = query.limit(args.max_db_documents)
            pending = await session.stream(query)
            valid_ids.update([str(id) async for (id,) in pending])
    if valid_ids:
        logging.info('Tagging: %s', valid_ids)
        cache = None
        try:
            cache = await emcache.create_client([emcache.MemcachedHostAddress(
                SETTINGS.memcache_url, SETTINGS.memcache_port)])
        except asyncio.TimeoutError as exc:
            logging.warning(exc)
        # tag(list(valid_ids)[0])
        #tasks = [tag_entry(id) for id in valid_ids]
        # await asyncio.gather(*tasks)
        for uid in valid_ids:
            await tag_entry(uid, cache)
        await cache.close()
        # await asyncio.to_thread(tag, valid_ids)

        # with Pool() as pool:  # issues with running out of memory due to forking/copy
        #    pool.map(tag, valid_ids)
    else:
        logging.info('No documents to tag.')
    if DRIVER is not None:
        await DRIVER.close()
    if ENGINE is not None:
        await ENGINE.dispose()

if __name__ == '__main__':
    asyncio.run(run_tagger(ARGS))
