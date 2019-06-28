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

#from default_settings import Config
from ds_tagger import create_tag_dict
import ds_db
import MSWord

PARSER = argparse.ArgumentParser(
    prog="docuscope-tagger.sif",
    description="Use DocuScope's Ity tagger to process a document in the database.")
PARSER.add_argument("uuid", nargs='*',
                    help="The id of a document in the DocuScope database.")
PARSER.add_argument("--db", help="URI of the database. <user>:<pass>@<url>:<port>/<database>",
                    default="docuscope:docuscope@127.0.0.1:3306/docuscope")
PARSER.add_argument('-c', '--check_db', action='store_true',
                    help="Check the database for any 'pending' documents.")
PARSER.add_argument('-v', '--verbose', help="Increase output verbosity.",
                    action="count", default=0)
ARGS = PARSER.parse_args()
LEVELS = [logging.WARNING, logging.INFO, logging.DEBUG]
logging.basicConfig(level=LEVELS[min(len(LEVELS)-1, ARGS.verbose)])
ENGINE = create_engine("mysql+mysqldb://{}".format(ARGS.db))
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

def tag_entry(doc_id):
    """Use DocuScope tagger on the specified document.
    Arguments:
    doc_id: a uuid of the document in the database.
    """
    doc_content = None
    ds_dict = "default"
    doc_processed = {"ERROR": "No file data to process."}
    doc_state = "error"
    ENGINE.dispose()
    logging.info("Trying to tag %s", doc_id)
    with session_scope() as session:
        qry = session.query(ds_db.Filesystem.content,
                            ds_db.DSDictionary.name)\
                     .filter(ds_db.Filesystem.id == doc_id)\
                     .filter(ds_db.Assignment.id == ds_db.Filesystem.assignment)\
                     .filter(ds_db.DSDictionary.id == ds_db.Assignment.dictionary)
        doc_content, ds_dict = qry.first()
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
            doc_processed = create_tag_dict(MSWord.toTOML(doc_content), ds_dict)
            doc_state = "tagged"
            logging.info("Successfully tagged %s", doc_id)
        except Exception as exc: #pylint: disable=W0703
            logging.error("Unsuccessfully tagged %s", doc_id)
            traceback.print_exc()
            doc_processed = {'error': "{0}".format(exc),
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

def run_tagger(args):
    """Gathers the document ids and runs the tagger on them (multitreaded)"""
    ids = {id for id in args.uuid if valid_uuid(id)}
    with session_scope() as session:
        valid_ids = {str(doc[0]) for doc in session.query(ds_db.Filesystem.id)
                     .filter(ds_db.Filesystem.id.in_(ids))}
        check_ids = ids.difference(valid_ids)
        if check_ids:
            logging.warning("Documents do not exist in database: %s", check_ids)
        if args.check_db:
            valid_ids.update([str(doc[0]) for doc in
                              session.query(ds_db.Filesystem.id)
                              .filter_by(state='pending')])
    logging.info('Tagging: %s', valid_ids)
    if valid_ids:
        with Pool() as pool:
            pool.map(tag_entry, valid_ids)

if __name__ == '__main__':
    run_tagger(ARGS)
