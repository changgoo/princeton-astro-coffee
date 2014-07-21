#!/usr/bin/env python

'''
arxivdb - Waqas Bhatti (wbhatti@astro.princeton.edu) - Jun 2014

Contains utilities for astroph-coffee server SQLite database manipulation for
inserting/modifying arXiv papers.

'''

import sqlite3
import os
import os.path
import ConfigParser
from datetime import datetime
from pytz import utc

# for text searching on author names
import difflib


CONF = ConfigParser.ConfigParser()
CONF.read('conf/astroph.conf')

DBPATH = CONF.get('sqlite3','database')

def opendb():
    '''
    This just opens a connection to the database and returns it + a cursor.

    '''

    db = sqlite3.connect(
        DBPATH, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES
        )

    cur = db.cursor()

    return db, cur


## LOCAL AUTHORS

def tag_local_authors(arxiv_date,
                      database=None,
                      match_threshold=0.83,
                      update_db=False):
    '''
    This finds all local authors for all papers on the date arxiv_date and tags
    the rows for them in the DB.

    '''

    # open the database if needed and get a cursor
    if not database:
        database, cursor = opendb()
        closedb = True
    else:
        cursor = database.cursor()
        closedb = False

    # get all local authors first
    query = 'select author from local_authors'
    cursor.execute(query)
    rows = cursor.fetchall()
    if rows and len(rows) > 0:
        local_authors = list(zip(*rows)[0])
        local_authors = [x.lower() for x in local_authors]
    else:
        local_authors = []

    if len(local_authors) > 0:

        # get all the authors for this date
        query = 'select arxiv_id, authors from arxiv where utcdate = date(?)'
        query_params = (arxiv_date,)
        cursor.execute(query, query_params)
        rows = cursor.fetchall()

        if rows and len(rows) > 0:

            local_author_articles = []

            for row in rows:

               paper_authors = row[1]
               paper_authors = (paper_authors.split(': ')[-1]).split(',')
               paper_authors = [x.lower() for x in paper_authors]

               for paper_author in paper_authors:

                   matched_author = difflib.get_close_matches(
                       paper_author,
                       local_authors,
                       n=1,
                       cutoff=match_threshold
                   )
                   if matched_author:

                       local_author_articles.append((row[0]))
                       print('%s: %s, matched paper author: %s '
                             'to local author: %s' % (row[0],
                                                      paper_authors,
                                                      paper_author,
                                                      matched_author))

                       if update_db:
                           cursor.execute('update arxiv '
                                          'set local_authors = ? where '
                                          'arxiv_id = ?', (True, row[0],))

                       break

            if update_db:
                database.commit()

            return local_author_articles

        else:

            print('no articles for this date')
            return False

    else:

        print('no local authors defined')
        return False

    # at the end, close the cursor and DB connection
    if closedb:
        cursor.close()
        database.close()



## INSERTING ARTICLES

def insert_articles(arxiv,
                    database=None,
                    tag_locals=True,
                    match_threshold=0.83):
    '''
    This inserts all articles in an arxivdict created by
    arxivutils.grab_arxiv_update into the astroph-coffee server database.

    '''

    # open the database if needed and get a cursor
    if not database:
        database, cursor = opendb()
        closedb = True
    else:
        cursor = database.cursor()
        closedb = False

    # make sure we know that the dt is in UTC
    arxiv_dt = arxiv['utc']
    if not arxiv_dt.tzinfo:
        arxiv_dt = arxiv_dt.replace(tzinfo=utc)


    papers = arxiv['papers']
    crosslists = arxiv['crosslists']

    query = ("insert or replace into arxiv (utctime, utcdate, "
             "day_serial, title, article_type,"
             "arxiv_id, authors, comments, abstract, link, pdf, "
             "nvotes, voters, presenters, local_authors) values "
             "(?,?, ?,?,?, ?,?,?,?,?,?, ?,?,?,?)")

    try:

        for key in papers:

            print('inserting astronomy article %s: %s' %
                  (key, papers[key]['title']))

            params = (arxiv_dt,
                      arxiv_dt.date(),
                      key,
                      papers[key]['title'],
                      'astronomy',
                      papers[key]['arxiv'],
                      ','.join(papers[key]['authors']),
                      papers[key]['comments'],
                      papers[key]['abstract'],
                      'http://arxiv.org%s' % papers[key]['link'],
                      'http://arxiv.org%s' % papers[key]['pdf'],
                      0,
                      '',
                      '',
                      False)
            cursor.execute(query, params)

        for key in crosslists:

            print('inserting cross-list article %s: %s' %
                  (key, papers[key]['title']))

            params = (arxiv_dt,
                      arxiv_dt.date(),
                      key,
                      papers[key]['title'],
                      'crosslists',
                      papers[key]['arxiv'],
                      ','.join(papers[key]['authors']),
                      papers[key]['comments'],
                      papers[key]['abstract'],
                      'http://arxiv.org%s' % papers[key]['link'],
                      'http://arxiv.org%s' % papers[key]['pdf'],
                      0,
                      '',
                      '',
                      False)
            cursor.execute(query, params)

        database.commit()

    except Exception as e:

        print('could not insert articles into the DB, error was %s' % e)
        database.rollback()

    # once we're done with the inserting articles bit, tag all local authors if
    # directed to do so
    if tag_locals:
        tag_local_authors(arxiv_dt.date(),
                          database=database,
                          match_threshold=match_threshold,
                          update_db=True)


    # at the end, close the cursor and DB connection
    if closedb:
        cursor.close()
        database.close()


## RETRIEVING ARTICLES

def get_articles_for_listing(utcdate,
                             database=None,
                             astronomyonly=True):
    '''

    This grabs all articles from the database for the given date for listing at
    /astroph-coffee/papers. Cross-lists are included in other_articles.

    Three lists are returned:

    (local_articles,
     voted_articles,
     other_articles)

    '''

    # open the database if needed and get a cursor
    if not database:
        database, cursor = opendb()
        closedb = True
    else:
        cursor = database.cursor()
        closedb = False

    local_articles, voted_articles, other_articles = [], [], []
    articles_excluded_from_other = []

    # deal with the local articles first
    if astronomyonly:
        query = ("select arxiv_id, day_serial, title, article_type, "
                 "authors, comments, abstract, link, pdf, nvotes, voters, "
                 "presenters, local_authors from arxiv where "
                 "utcdate = date(?) and local_authors = 1 "
                 "and article_type = 'astronomy' "
                 "order by nvotes desc")
    else:
        query = ("select arxiv_id, day_serial, title, article_type, "
                 "authors, comments, abstract, link, pdf, nvotes, voters, "
                 "presenters, local_authors from arxiv where "
                 "utcdate = date(?) and local_authors = 1 "
                 "order by nvotes desc")

    query_params = (utcdate,)
    cursor.execute(query, query_params)
    rows = cursor.fetchall()

    if len(rows) > 0:
        for row in rows:
            local_articles.append(row)
            articles_excluded_from_other.append(row[0])

    # deal with articles that have votes next
    if astronomyonly:
        query = ("select arxiv_id, day_serial, title, article_type, "
                 "authors, comments, abstract, link, pdf, nvotes, voters, "
                 "presenters, local_authors from arxiv where "
                 "utcdate = date(?) and nvotes > 0 "
                 "and article_type = 'astronomy' "
                 "order by nvotes desc")
    else:
        query = ("select arxiv_id, day_serial, title, article_type, "
                 "authors, comments, abstract, link, pdf, nvotes, voters, "
                 "presenters, local_authors from arxiv where "
                 "utcdate = date(?) and nvotes > 0 "
                 "order by nvotes desc")

    query_params = (utcdate,)
    cursor.execute(query, query_params)
    rows = cursor.fetchall()

    if len(rows) > 0:
        for row in rows:
            voted_articles.append(row)
            articles_excluded_from_other.append(row[0])

    # finally deal with the other articles
    if len(articles_excluded_from_other) > 0:

        if astronomyonly:
            query = ("select arxiv_id, day_serial, title, article_type, "
                     "authors, comments, abstract, link, pdf, nvotes, voters, "
                     "presenters, local_authors from arxiv where "
                     "utcdate = date(?) and "
                     "arxiv_id not in ({exclude_list}) "
                     "and article_type = 'astronomy' "
                     "order by day_serial asc")
        else:
            query = ("select arxiv_id, day_serial, title, article_type, "
                     "authors, comments, abstract, link, pdf, nvotes, voters, "
                     "presenters, local_authors from arxiv where "
                     "utcdate = date(?) and "
                     "arxiv_id not in ({exclude_list}) "
                     "order by article_type asc, day_serial asc")

        placeholders = ', '.join('?' for x in articles_excluded_from_other)
        query = query.format(exclude_list=placeholders)
        query_params = tuple([utcdate] + articles_excluded_from_other)

    else:

        if astronomyonly:
            query = ("select arxiv_id, day_serial, title, article_type, "
                     "authors, comments, abstract, link, pdf, nvotes, voters, "
                     "presenters, local_authors from arxiv where "
                     "utcdate = date(?) "
                     "and article_type = 'astronomy' "
                     "order by day_serial asc")
        else:
            query = ("select arxiv_id, day_serial, title, article_type, "
                     "authors, comments, abstract, link, pdf, nvotes, voters, "
                     "presenters, local_authors from arxiv where "
                     "utcdate = date(?) "
                     "order by article_type asc, day_serial asc")

        query_params = (utcdate,)

    cursor.execute(query, query_params)
    rows = cursor.fetchall()

    if len(rows) > 0:
        for row in rows:
            other_articles.append(row)


    # at the end, close the cursor and DB connection
    if closedb:
        cursor.close()
        database.close()

    return (local_articles, voted_articles, other_articles)



def get_articles_for_voting(database=None,
                            astronomyonly=True):
    '''
    This grabs all articles from the database for today's date to show for
    voting. The articles are sorted in arxiv_id order with papers and
    cross_lists returned separately.

    '''

    # open the database if needed and get a cursor
    if not database:
        database, cursor = opendb()
        closedb = True
    else:
        cursor = database.cursor()
        closedb = False

    # this is today's date
    utcdate = datetime.now(tz=utc).strftime('%Y-%m-%d')


    local_articles, other_articles = [], []
    articles_excluded_from_other = []

    # deal with the local articles first
    if astronomyonly:
        query = ("select arxiv_id, day_serial, title, article_type, "
                 "authors, comments, abstract, link, pdf, nvotes, voters, "
                 "presenters, local_authors from arxiv where "
                 "utcdate = date(?) and local_authors = 1 "
                 "and article_type = 'astronomy' "
                 "order by nvotes desc")
    else:
        query = ("select arxiv_id, day_serial, title, article_type, "
                 "authors, comments, abstract, link, pdf, nvotes, voters, "
                 "presenters, local_authors from arxiv where "
                 "utcdate = date(?) and local_authors = 1 "
                 "order by nvotes desc")
    query_params = (utcdate,)
    cursor.execute(query, query_params)
    rows = cursor.fetchall()

    if len(rows) > 0:
        for row in rows:
            local_articles.append(row)
            articles_excluded_from_other.append(row[0])

    # finally deal with the other articles
    if len(articles_excluded_from_other) > 0:

        if astronomyonly:
            query = ("select arxiv_id, day_serial, title, article_type, "
                     "authors, comments, abstract, link, pdf, nvotes, voters, "
                     "presenters, local_authors from arxiv where "
                     "utcdate = date(?) and "
                     "arxiv_id not in ({exclude_list}) "
                     "and article_type = 'astronomy' "
                     "order by day_serial asc")
        else:
            query = ("select arxiv_id, day_serial, title, article_type, "
                     "authors, comments, abstract, link, pdf, nvotes, voters, "
                     "presenters, local_authors from arxiv where "
                     "utcdate = date(?) and "
                     "arxiv_id not in ({exclude_list}) "
                     "order by article_type asc, day_serial asc")

        placeholders = ', '.join('?' for x in articles_excluded_from_other)
        query = query.format(exclude_list=placeholders)
        query_params = tuple([utcdate] + articles_excluded_from_other)

    else:

        if astronomyonly:
            query = ("select arxiv_id, day_serial, title, article_type, "
                     "authors, comments, abstract, link, pdf, nvotes, voters, "
                     "presenters, local_authors from arxiv where "
                     "utcdate = date(?) "
                     "and article_type = 'astronomy' "
                     "order by day_serial asc")
        else:
            query = ("select arxiv_id, day_serial, title, article_type, "
                     "authors, comments, abstract, link, pdf, nvotes, voters, "
                     "presenters, local_authors from arxiv where "
                     "utcdate = date(?) "
                     "order by article_type asc, day_serial asc")

        query_params = (utcdate,)

    cursor.execute(query, query_params)
    rows = cursor.fetchall()

    if len(rows) > 0:
        for row in rows:
            other_articles.append(row)

    # at the end, close the cursor and DB connection
    if closedb:
        cursor.close()
        database.close()

    return (local_articles, other_articles)



## VOTERS AND PRESENTERS

def record_vote(arxiv_id, votername, vote, database=None):
    '''
    This records votes for a paper in the DB.

    '''

    # open the database if needed and get a cursor
    if not database:
        database, cursor = opendb()
        closedb = True
    else:
        cursor = database.cursor()
        closedb = False





    # at the end, close the cursor and DB connection
    if closedb:
        cursor.close()
        database.close()



def modify_presenters(arxiv_id, presenter, action, database=None):
    '''
    This adds/removes presenters for a paper.

    action = 'add' -> adds person named presenter
    action = 'remove' -> removes person named presenter

    '''

    # open the database if needed and get a cursor
    if not database:
        database, cursor = opendb()
        closedb = True
    else:
        cursor = database.cursor()
        closedb = False





    # at the end, close the cursor and DB connection
    if closedb:
        cursor.close()
        database.close()