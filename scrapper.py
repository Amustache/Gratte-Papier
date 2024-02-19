import arxiv
from scholarly import scholarly
import pandas as pd
import re
import boolean
import string
from tqdm.auto import tqdm
import asyncio

COOLDOWN = 5
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
        expression = expression.replace(word, f"all:{word}")

    expression = expression \
        .replace("&~", " ANDNOT ") \
        .replace("~", " ANDNOT ") \
        .replace("&", " AND ") \
        .replace("|", " OR ") \
        .replace("_", " ")

    return expression


def expression_to_scolar_query(expression):
    for word in set(re.findall(r"(\w+)", expression)):
        expression = expression.replace(word, f"\"{word.replace('_', ' ')}\"" if "_" in word else word)

    expression = expression \
        .replace("&~", " -") \
        .replace("~", " -") \
        .replace("&", " ") \
        .replace("|", " OR ")

    return expression


async def arxiv_query_to_dataframe(query, max_results=MAX_RESULTS, num_retries=NUM_RETRIES, cooldown=COOLDOWN):
    client = arxiv.Client(num_retries=num_retries)
    search = arxiv.Search(query=query, max_results=max_results)
    results = client.results(search)

    df = pd.DataFrame()

    for i, result in enumerate(tqdm(results, desc="arxiv")):
        next_row = pd.Series({
            "doi": f"10.48550/arXiv.{result.entry_id.split('/')[-1].split('v')[0]}",
            "year": result.published.year,
            "title": result.title,
            "authors": result.authors,
            "abstract": result.summary,
            "journal": result.journal_ref,
            "url_pdf": [link.href for link in result.links if link.title == "pdf"][0],
            "url_others": [{link.title or "canonical": link.href for link in result.links if link.title != "pdf"}],
            "from": "arXiv",
        }).to_frame().T
        df = pd.concat([df, next_row], ignore_index=True)
        if not i % cooldown:
            await asyncio.sleep(cooldown)
        if i == max_results - 1:
            break

    yield df


async def scolar_query_to_dataframe(query, max_results=MAX_RESULTS, num_retries=NUM_RETRIES, cooldown=COOLDOWN):
    results = scholarly.search_pubs(query)

    df = pd.DataFrame()

    for i, result in enumerate(tqdm(results, desc="scolar")):
        next_row = pd.Series({
            "doi": None,  # No DOI on Google Scholar
            "year": result.bib.get("year", None),
            "title": result.bib.get("title", None),
            "authors": result.bib.get("author", None),
            "abstract": result.bib.get("abstract", None),
            "journal": result.bib.get("venue", None),
            "url_pdf": result.bib.get("eprint", None),
            "url_others": [{
                "canonical": f"https://scholar.google.com{result.citations_link}",
                "source": result.bib.get("url", None)
            }],
            "from": "Google Scholar",
        }).to_frame().T
        df = pd.concat([df, next_row], ignore_index=True)
        if not i % 10:
            await asyncio.sleep(cooldown)
        if i == max_results - 1:
            break

    yield df
