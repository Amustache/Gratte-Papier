import os

import arxiv
from scholarly import scholarly
import pandas as pd
import re
import boolean
import string

if os.path.isfile("config.py"):
    from config import WOS_API_KEY
else:
    WOS_API_KEY = None

COOLDOWN = 5
BATCH_RESULTS = 10
NUM_RETRIES = 10
MAX_RESULTS = 100
SCRAPPER_COLUMNS = {
    "doi": "DOI",
    "year": "Year",
    "title": "Title",
    "authors": "Authors",
    "abstract": "Abstract",
    "journal": "Journal",
    "url_pdf": "URL to PDF",
    "url_others": "Other URLs",
    "from": "Source",
}


def prep_expression(request):
    # NOT > AND > OR
    text = " ".join(request.lower().replace(" -", " and not ").replace("\"", "'").split()) + " "

    for q in re.findall(r"(\'.*?\')", text):
        t = q[:-1].replace("'", "").replace(" ", "_")
        text = text.replace(q, t) + " "

    for p in string.punctuation:
        if p != "(" and p != ")":
            text = text.replace(p, "_")

    text = text.replace(" and ", "&").replace(" or ", "|").replace("not ", "~").strip().replace(" ", "&")

    algebra = boolean.BooleanAlgebra()

    expression = algebra.parse(text, simplify=True)

    return str(expression)


def expression_to_arxiv_query(expression):
    for word in set(re.findall(r"(\w+)", expression)):
        expression = expression.replace(word, f"all:{word.replace('_', ' ')}")

    expression = expression \
        .replace("&~", " ANDNOT ") \
        .replace("~", " ANDNOT ") \
        .replace("&", " AND ") \
        .replace("|", " OR ") \

    return expression


def arxiv_query_to_generator(query, max_results=MAX_RESULTS, num_retries=NUM_RETRIES):
    client = arxiv.Client(num_retries=num_retries)
    search = arxiv.Search(query=query, max_results=max_results)
    gen = client.results(search)

    return gen


def arxiv_result_to_dataframe(result, query=None, initial_request=None):
    next_row = pd.Series({
        "doi": f"10.48550/arXiv.{result.entry_id.split('/')[-1].split('v')[0]}",
        "year": result.published.year,
        "title": result.title,
        "authors": ";".join(str(author) for author in result.authors),
        "abstract": result.summary,
        "journal": result.journal_ref,
        "url_pdf": [link.href for link in result.links if link.title == "pdf"][0],
        "url_others": ";".join(
            [f"{link.title or 'canonical'}:{link.href}" for link in result.links if link.title != "pdf"]
        ),
        "from": "arXiv",
        "initial_query": initial_request,
        "arxiv_query": query,
    }).to_frame().T

    return next_row


def expression_to_scholar_query(expression):
    for word in set(re.findall(r"(\w+)", expression)):
        expression = expression.replace(word, f"\"{word.replace('_', ' ')}\"" if "_" in word else word)

    expression = expression \
        .replace("&~", " -") \
        .replace("~", " -") \
        .replace("&", " ") \
        .replace("|", " OR ")

    return expression


def scholar_query_to_generator(query, max_results=MAX_RESULTS, num_retries=NUM_RETRIES):
    gen = scholarly.search_pubs(query)

    return gen


def scholar_result_to_dataframe(result, query=None, initial_request=None):
    next_row = pd.Series({
        "doi": None,  # No DOI on Google Scholar
        "year": result.bib.get("year", None),
        "title": result.bib.get("title", None),
        "authors": ";".join(result.bib.get("author", None)),
        "abstract": result.bib.get("abstract", None),
        "journal": result.bib.get("venue", None),
        "url_pdf": result.bib.get("eprint", None),
        "url_others": f"canonical:https://scholar.google.com{result.citations_link};source:{result.bib.get('url', None)}"
        if hasattr(result, "citations_link")
        else f"source:{result.bib.get('url', None)}",
        "from": "Google Scholar",
        "initial_query": initial_request,
        "scholar_query": query,
    }).to_frame().T

    return next_row


def expression_to_wos_query(expression):
    for word in set(re.findall(r"(\w+)", expression)):
        expression = expression.replace(word, f"ALL:({word.replace('_', ' ')})")

    expression = expression \
        .replace("&~", " NOT ") \
        .replace("~", " NOT ") \
        .replace("&", " AND ") \
        .replace("|", " OR ") \

    return expression


def wos_query_to_generator(query, max_results=MAX_RESULTS, num_retries=NUM_RETRIES):
    raise NotImplementedError


def wos_result_to_dataframe(result, query=None, initial_request=None):
    raise NotImplementedError


SUPPORTED_PLATFORMS = {
    "arxiv": {
        "name": "arXiv",
        "fun_query": expression_to_arxiv_query,
        "fun_generator": arxiv_query_to_generator,
        "fun_format": arxiv_result_to_dataframe,
        "tooltip": None,
        "disabled": False,
    },
    "scholar": {
        "name": "Google Scholar",
        "fun_query": expression_to_scholar_query,
        "fun_generator": scholar_query_to_generator,
        "fun_format": scholar_result_to_dataframe,
        "tooltip": "Ne donne pas le DOI de l'entrée.",
        "disabled": False,
    },
    "wos": {
        "name": "Web of Science",
        "fun_query": expression_to_wos_query,
        "fun_generator": wos_query_to_generator,
        "fun_format": wos_result_to_dataframe,
        "tooltip": f"Limitation de deux requêtes par seconde, 50'000 entrées par an.{' Nécessite une clé API.' if WOS_API_KEY is None else ''}",
        "disabled": WOS_API_KEY is None,
    }
}
