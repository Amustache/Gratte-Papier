import os
import time

import arxiv
from dash import Dash, html, dcc, Output, Input, dash_table, DiskcacheManager, CeleryManager
import dash_bootstrap_components as dbc
import pandas as pd
from dash.exceptions import PreventUpdate
from scholarly import scholarly

from scrapper import SCRAPPER_COLUMNS, prep_expression, expression_to_arxiv_query, expression_to_scolar_query, COOLDOWN, \
    NUM_RETRIES

import gettext

# i18n / Translation
for language in ["fr"]:
    language_translations = gettext.translation("base", "locales", languages=[language])
    language_translations.install()

_ = language_translations.gettext

# Cache for background callback
if 'REDIS_URL' in os.environ:
    # Use Redis & Celery if REDIS_URL set as an env variable
    from celery import Celery

    celery_app = Celery(__name__, broker=os.environ["REDIS_URL"], backend=os.environ["REDIS_URL"])
    background_callback_manager = CeleryManager(celery_app)
else:
    # Diskcache for non-production apps when developing locally
    import diskcache

    cache = diskcache.Cache("./cache")
    background_callback_manager = DiskcacheManager(cache)

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    background_callback_manager=background_callback_manager
)

# Control panel on the left
controls = dbc.Card([
    # Options
    dbc.CardBody(dbc.Form([
        html.Div([
            dbc.Label(_("Keywords to include (AND, OR)"), html_for="keywords_include"),
            dbc.Input(
                id="keywords_include",
                placeholder=_("e.g., \"(Machine Learning) OR (Apprentissage Automatisé)\""),
                type="text"
            ),
        ]),
        html.Div([
            dbc.Label(_("Keywords to exclude (NOT)"), html_for="keywords_exclude"),
            dbc.Input(
                id="keywords_exclude",
                placeholder=_("e.g., \"Deep Learning\""),
                type="text"
            ),
        ]),
        html.Div([
            dbc.Label("Platforms", html_for="platforms"),
            dbc.Checklist(
                options=[
                    {"label": "arXiv", "value": "arxiv"},
                    {"label": "Google Scholar", "value": "scholar"},
                ],
                value=[],
                id="platforms",
                inline=True,
                switch=True,
            ),
        ]),
        html.Div([
            dbc.Label(_("Number of results (per platform)"), html_for="max_results"),
            dbc.Input(id="max_results", type="number", value=100, min=0, step=1),
        ]),
        html.Div([
            dbc.Button(_("Cancel"), id="cancel_button", color="secondary", className="mt-2 me-2 disabled"),
            dbc.Button(_("Search"), id="search_button", color="success", className="mt-2"),
        ], className="float-end")
    ])),

    # Information
    dbc.CardFooter([
        html.Dl(id="infos", className="row"),
        dbc.Progress(id="progress", animated=True, striped=True, style={"visibility": "hidden"}),
    ]),
])

# Results
table = dash_table.DataTable(
    id="datatable",
    data=None,  # Dynamic
    columns=[{"name": v, "id": k} for k, v in SCRAPPER_COLUMNS.items()],
    style_cell={
        "overflow": "hidden",
        "textOverflow": "ellipsis",
        "maxWidth": 0,
    },
    tooltip_data=None,  # Dynamic
    tooltip_duration=None,
    filter_action="native",
    sort_action="native",
    sort_mode="multi",
    row_selectable="multi",
    selected_columns=[],
    selected_rows=[],
    page_action="native",
    page_current=0,
    page_size=10,
)

app.layout = dbc.Container(
    [
        html.H1("Gratte-Papier"),
        html.Hr(),
        dbc.Row([
            dbc.Col(controls, md=4),
            dbc.Col([
                table,
                html.Div([
                    dbc.Button(_("Download selected (Excel)"), id="dl_selected", color="secondary",
                               className="mt-2 me-2"),
                    dbc.Button(_("Download all (Excel)"), id="dl_all", color="primary", className="mt-2"),
                ], className="float-end")
            ], md=8),
        ]),
        dcc.Interval(id="interval", disabled=True),
        dcc.Store(id="data_store"),
    ],
    fluid=True,
)


def human_time(seconds):
    """
    Simple transform from seconds to human read time.

    :param seconds: Seconds
    :return: Done, or minutes left, or hours left.
    """
    if seconds <= 0:
        return _("Done!")
    if seconds < 60:
        return _("Less than one minute left")
    else:
        minutes = round(seconds / 60)
        if minutes < 60:
            return _("About {} minute{} left").format(minutes, "s" if minutes != 1 else "")
        else:
            hours = round(minutes / 60)
            return _("About {} hour{} left").format(hours, "s" if hours != 1 else "")


@app.callback(
    Output("search_button", "n_clicks"),
    Output("infos", "children"),
    Output("data_store", "data"),
    Input("search_button", "n_clicks"),
    Input("keywords_include", "value"),
    Input("keywords_exclude", "value"),
    Input("platforms", "value"),
    Input("max_results", "value"),
)
def start_scrapping(n, included, excluded, platforms, max_results):
    """
    Generate requests, and store them in the datastore, which triggers the scrapping.
    """
    if n and included and platforms and max_results > 0:
        children = [
            html.Dt(_("Entries found"), className="col-4"),
            html.Dd("0", id="found", className="col-8"),
        ]
        data = {}

        included = included.lower() if included else ""
        excluded = " ".join(
            [f" not {word}" for word in excluded.lower().replace("not", " ").split(" ")]) if excluded else ""

        expression = prep_expression(included + excluded)
        children += [
            html.Dt(_("Expression"), className="col-4"),
            html.Dd(html.Pre(expression), id="expression", className="col-8"),
        ]
        data["expression"] = expression

        if "arxiv" in platforms:
            arxiv_query = expression_to_arxiv_query(expression)
            children += [
                html.Dt(_("ArXiv request"), className="col-4"),
                html.Dd(html.Pre(arxiv_query), id="r_arxiv", className="col-8"),
            ]
            data["arxiv_query"] = arxiv_query

        if "scholar" in platforms:
            scolar_query = expression_to_scolar_query(expression)
            children += [
                html.Dt(_("Google Scholar request"), className="col-4"),
                html.Dd(html.Pre(scolar_query), id="r_scholar", className="col-8"),
            ]
            data["scolar_query"] = scolar_query

        max_time = len(platforms) * max_results
        children += [
            html.Dt(_("Estimated time left"), className="col-4"),
            html.Dd(human_time(max_time), id="estimated", className="col-8"),
        ]
        data["max_results"] = max_results
        data["max_time"] = max_time

        return 0, children, data
    else:
        raise PreventUpdate


@app.callback(
    Output("datatable", "data"),
    Output("datatable", "tooltip_data"),
    Input("data_store", "data"),
    background=True,
    running=[
        (Output("search_button", "disabled"), True, False),
        (Output("cancel_button", "disabled"), False, True),
        (
                Output("progress", "style"),
                {"visibility": "visible"},
                {"visibility": "hidden"},
        )
    ],
    cancel=Input("cancel_button", "n_clicks"),
    progress=[
        Output("progress", "value"),
        Output("progress", "max"),
        Output("found", "children"),
        Output("estimated", "children"),
    ],
    prevent_initial_call=True,
)
def process_scrapping(set_progress, data):
    """
    Actual scrapping, happening in background, while updating the front.
    """
    arxiv_query = data["arxiv_query"] if "arxiv_query" in data else None
    scolar_query = data["scolar_query"] if "scolar_query" in data else None
    max_results = data["max_results"] if "max_results" in data else None
    cur_est_total = max_results * ((arxiv_query is not None) + (scolar_query is not None))
    cur_est_time = cur_est_total * ((arxiv_query is not None) + (scolar_query is not None))

    df = pd.DataFrame()

    if arxiv_query:
        client = arxiv.Client(num_retries=NUM_RETRIES)
        search = arxiv.Search(query=arxiv_query, max_results=max_results)
        arxiv_gen = client.results(search)

        for i, result in enumerate(arxiv_gen):
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
            }).to_frame().T
            df = pd.concat([df, next_row], ignore_index=True)
            cur_len = len(df.index)
            cur_est_time -= 1

            if not (i + 1) % COOLDOWN:
                set_progress((
                    str(cur_len),
                    str(cur_est_total),
                    str(cur_len),
                    str(human_time(cur_est_time)),
                ))
                time.sleep(COOLDOWN)

            if i == max_results - 1:
                break

    cur_est_total = len(df.index) + max_results * (scolar_query is not None)

    if scolar_query:
        scolar_gen = scholarly.search_pubs(scolar_query)

        for i, result in enumerate(scolar_gen):
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
            }).to_frame().T
            df = pd.concat([df, next_row], ignore_index=True)
            cur_len = len(df.index)
            cur_est_time -= 1

            if i == max_results - 1:
                break

            if not (i + 1) % COOLDOWN:
                set_progress((
                    str(cur_len),
                    str(cur_est_total),
                    str(cur_len),
                    str(human_time(cur_est_time)),
                ))
                time.sleep(COOLDOWN)

    set_progress((
        str(len(df.index)),
        str(len(df.index)),
        str(len(df.index)),
        str(human_time(0)),
    ))

    tooltip_data = [
        {
            column: {"value": str(value), "type": "markdown"}
            for column, value in row.items()
        } for row in df.to_dict("records")
    ]

    return df.to_dict(orient="records"), tooltip_data


if __name__ == "__main__":
    app.run(debug=True)
