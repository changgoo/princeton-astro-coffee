import arxivutils, arxivdb
from datetime import datetime
import requests
import time

def update_arxiv(fullname_match_threshold=72, firstname_match_threshold=93):
    x = arxivutils.arxiv_update(fakery=False)
    arxivdb.insert_articles(x,
                            fullname_match_threshold=fullname_match_threshold,
                            firstname_match_threshold=firstname_match_threshold)

def arxiv_updated(timeout=600, num_tries=30):
    search_string = "announced "+datetime.utcnow().strftime("%a, %d %b %y")
    date = datetime.now().strftime("%Y-%m-%d")
    search_string = "<dc:date>%sT20:30:00" % (date,)
    for n in range(num_tries):
        resp = requests.get("https://arxiv.org/rss/astro-ph")
        time.sleep(timeout)
        # Delay the return because the actual list updates after the rss feed
        if search_string in resp.text:
            return True

    return False

if __name__=='__main__':
    if arxiv_updated():
        update_arxiv()

