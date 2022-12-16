"""
Basic data analysis functions.

A collection of functions that produce various summary statistics over the collected
tagging data.
"""
import asyncio
from collections import Counter
import json

from pandas import DataFrame, Interval, Timestamp
from pandas.arrays import IntervalArray
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .database import Tagging
from .default_settings import SQLALCHEMY_DATABASE_URI


async def tagger_performance(sql: AsyncSession):
    """Prints out performance statistics for the online DocuScope tagger."""
    # TODO add time constraints (eg) WHERE TIMESTAMP('2022-09-26') <= started
    query = await sql.execute(select(Tagging).order_by(Tagging.started))
    data = DataFrame([[
            data.state,
            data.word_count,
            Interval(left=Timestamp(data.started), right=Timestamp(data.finished), closed='both')]
          for data in query.scalars()],
        columns=['state', 'word_count', 'interval'])
    # print(df)
    print('--- States ---')
    print(data['state'].value_counts())
    print('--- TimeDelta ---')
    data['delta'] = data['interval'].apply(lambda i: i.length.total_seconds())
    #print(df['interval'].apply(lambda i: i.length).describe())
    print(data['delta'].describe())
    print('--- Word Count ---')
    print(data['word_count'].describe())
    print('--- Words/sec ---')
    data['words_per_second'] = data['word_count'] / data['delta']
    print(data['words_per_second'].describe())
    #out = df['count'].describe() + df['delta'] + df['wc_delta']
    out = {}
    out['describe'] = data.describe().to_dict()
    out['state'] = data['state'].value_counts().to_dict()

    intervals = IntervalArray(data['interval'])
    data['overlap'] = (data.loc[:, 'interval']).apply(
        lambda i: intervals.overlaps(i).sum()-1)
    out['overlaps'] = data['overlap'].value_counts().tolist()
    print(json.dumps(out))

# async def classroom_performance(sql: AsyncSession):
#    query = await sql.execute(select(
# Submission.assignment,
#  Submission.owner,
#  Submission.created,
#  Submission.fullname,
#  Submission.state,
#  Submission.ownedby,
#  Submission.processed))
#    df = DataFrame([[
#        data.state,
#        data.assignment,
#        data.owner,
#        data.ownedby,
#        data.fullname,
#        data.created
#    ] for data in query.scalars()])
#    print(df)


async def tagger_analysis(sql: AsyncSession):
    """Prints out various pattern and category counts."""
    tagging = await sql.stream_scalars(select(Tagging).where(Tagging.state == 'success'))
    patterns = Counter()
    categories = Counter()
    async for row in tagging:
        data = row.detail
        for category in data['patterns']:
            if category['category'] != '?':
                cat_count = Counter({pat['pattern']: pat['count']
                                    for pat in category['patterns']})
                patterns.update(cat_count)
                categories.update({category['category']: cat_count.total()})
    print(f"10 Most common patterns: {patterns.most_common(10)}")
    if len(patterns) > 0:
        longest = max(patterns.keys(), key=lambda i: len(i.split(' ')))
        print(f'Longest pattern: "{longest}" count: {patterns[longest]}')
    print(f"Category frequency: {categories.most_common()}")
    return


async def async_main():
    """Main function for running the various metrics asyncroniously."""
    engine = create_async_engine(SQLALCHEMY_DATABASE_URI)
    async_session = sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        await tagger_performance(session)
        # await classroom_performance(session)
        await tagger_analysis(session)
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(async_main())
