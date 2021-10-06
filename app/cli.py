"""Command line interface for DocuScope Tagger.
Run with --help to see options.
"""
import argparse
from contextlib import contextmanager
import logging
from multiprocessing import Pool
import traceback
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from default_settings import Config
from ds_tagger import create_ds_tagger, tag_dict
import ds_db
import MSWord

PARSER = argparse.ArgumentParser(
    prog="docuscope-tagger.sif",
    description="Use DocuScope's Ity tagger to process a document in the database.")
PARSER.add_argument("uuid", nargs='*',
                    help="The id of a document in the DocuScope database.")
# no default in following so as to not reveal password.
PARSER.add_argument(
    "--db",
    help="URI of the database. <user>:<pass>@<url>:<port>/<database>")
PARSER.add_argument('-c', '--check_db', action='store_true',
                    help="Check the database for any 'pending' documents.")
PARSER.add_argument('-m', '--max_db_documents', type=int, default=-1,
                    help="Maximum number of 'pending' documents to process.")
PARSER.add_argument('-v', '--verbose', help="Increase output verbosity.",
                    action="count", default=0)
ARGS = PARSER.parse_args()
LEVELS = [logging.WARNING, logging.INFO, logging.DEBUG]
logging.basicConfig(level=LEVELS[min(len(LEVELS)-1, ARGS.verbose)])
ENGINE = None
if ARGS.db:
    logging.info('Database settings from args')
    ENGINE = create_engine(f"mysql+mysqldb://{ARGS.db}")
else:
    logging.info('Database settings env')
    ENGINE = create_engine(Config.SQLALCHEMY_DATABASE_URI)
SESSION = sessionmaker(bind=ENGINE)

@contextmanager
def session_scope():
    """Establish a scoped session for accessing the database."""
    session = SESSION()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()

def tag_entry(tagger, doc_id):
    """Use DocuScope tagger on the specified document.
    Arguments:
    doc_id: a uuid of the document in the database.
    """
    doc_content = None
    # ds_dict = "default"
    doc_processed = {"ERROR": "No file data to process."}
    doc_state = "error"
    ENGINE.dispose()
    logging.info("Trying to tag %s", doc_id)
    with session_scope() as session:
        # Removed retrieval of dictionary name.  Unused and NULL values crash #7
        (doc_content,) = session.query(ds_db.Filesystem.content)\
                     .filter(ds_db.Filesystem.id == doc_id).first()
        if doc_content:
            session.query(ds_db.Filesystem)\
               .filter(ds_db.Filesystem.id == doc_id)\
               .update({"state": "submitted"},
                       synchronize_session=False)
        else:
            logging.error("Could not load %s!", doc_id)
            raise FileNotFoundError(doc_id)
    if doc_content:
        try:
            doc_processed = tag_dict(tagger.tag_string(MSWord.toTOML(doc_content)))
            if doc_processed.get('ds_num_word_tokens', 0) == 0:
                doc_state = "error"
                doc_processed['error'] = 'Document failed to parse: no word tokens found.'
                logging.error("Invalid parsing results %s", doc_id)
            else:
                doc_state = "tagged"
                logging.info("Successfully tagged %s", doc_id)
        except Exception as exc: #pylint: disable=W0703
            logging.error("Unsuccessfully tagged %s", doc_id)
            traceback.print_exc()
            doc_processed = {'error': f"{exc}",
                             'trace': traceback.format_exc()}
            doc_state = "error"
    with session_scope() as session:
        session.query(ds_db.Filesystem)\
               .filter_by(id=doc_id)\
               .update({"processed": doc_processed,
                        "state": doc_state})
    logging.info("Finished tagging %s", doc_id)

def valid_uuid(doc_id):
    """Check if the given document id is a uuid string."""
    try:
        uuid.UUID(doc_id)
        return True
    except ValueError as vexc:
        logging.warning("%s: %s", vexc, doc_id)
        return False

TAGGER = None

def tag(doc_id):
    """ Wrapper function for tag_entry that includes the tagger. """
    return tag_entry(TAGGER, doc_id)

def run_tagger(args):
    """Gathers the document ids and runs the tagger on them (multitreaded)"""
    ids = {id for id in args.uuid if valid_uuid(id)} # only uuids
    with session_scope() as session:
        # check if uuids are in database
        valid_ids = {str(doc[0]) for doc in session.query(ds_db.Filesystem.id)
                     .filter(ds_db.Filesystem.id.in_(ids))}
        check_ids = ids.difference(valid_ids)
        if check_ids:
            logging.warning("Documents do not exist in database: %s", check_ids)
        # If checking the database for 'pending' documents,
        # add all (limit max number) pending documents to list of ids
        if args.check_db:
            if args.max_db_documents > 0:
                valid_ids.update([str(doc[0]) for doc in
                                  session.query(ds_db.Filesystem.id)
                                  .filter_by(state='pending')
                                  .limit(args.max_db_documents)])

            else:
                valid_ids.update([str(doc[0]) for doc in
                                  session.query(ds_db.Filesystem.id)
                                  .filter_by(state='pending')])
    if valid_ids:
        # Create the tagger using default dictionary.
        logging.info('Loading dictionary: %s', Config.DICTIONARY)
        # Needs to be global to share as functools.partial does not work.
        global TAGGER #pylint: disable=global-statement
        TAGGER = create_ds_tagger(Config.DICTIONARY)
        logging.info('Loaded dictionary: %s', Config.DICTIONARY)
        logging.info('Tagging: %s', valid_ids)
        with Pool() as pool:
            pool.map(tag, valid_ids)
    else:
        logging.info('No documents to tag.')

if __name__ == '__main__':
    run_tagger(ARGS)
