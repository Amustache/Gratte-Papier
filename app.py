import os
import gettext
import time

from dash import Dash, html, dcc, Output, Input, dash_table, DiskcacheManager, CeleryManager, State
import dash_bootstrap_components as dbc
import pandas as pd
from dash.exceptions import PreventUpdate

from scrapper import SCRAPPER_COLUMNS, prep_expression, COOLDOWN, BATCH_RESULTS, SUPPORTED_PLATFORMS

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
                options=[{"label": v["name"], "value": k} for k, v in SUPPORTED_PLATFORMS.items()],
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
        dcc.Download(id="download"),
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
        data = {"query": {}}

        included = included.lower() if included else ""
        excluded = " ".join(
            [f" not {word}" for word in excluded.lower().replace("not", " ").split(" ")]) if excluded else ""
        final = included + excluded
        data["input"] = final

        expression = prep_expression(final)
        children += [
            html.Dt(_("Expression"), className="col-4"),
            html.Dd(html.Pre(expression), id="expression", className="col-8"),
        ]
        data["expression"] = expression

        for platform in platforms:
            query = SUPPORTED_PLATFORMS[platform]["fun_query"](expression)
            children += [
                html.Dt(_(f"{SUPPORTED_PLATFORMS[platform]['name']} request"), className="col-4"),
                html.Dd(html.Pre(query), id=f"r_{platform}", className="col-8"),
            ]
            data["query"][platform] = query

        max_time = len(platforms) * (max_results // BATCH_RESULTS) * COOLDOWN
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
    initial_request = data["input"] if "input" in data else None
    max_results = data["max_results"] if "max_results" in data else 0
    cur_est_time = data["max_time"] if "max_time" in data else 0

    df = pd.DataFrame()

    for i_platform, (platform, query) in enumerate(data["query"].items()):
        cur_est_total = len(df.index) + max_results * (len(data["query"]) - i_platform)

        gen_results = SUPPORTED_PLATFORMS[platform]["fun_generator"](query)

        for i, result in enumerate(gen_results):
            next_row = SUPPORTED_PLATFORMS[platform]["fun_format"](result, query, initial_request)
            df = pd.concat([df, next_row], ignore_index=True)
            cur_len = len(df.index)

            if i == max_results - 1:  # We are done
                break

            if not (i + 1) % BATCH_RESULTS:
                set_progress((
                    str(cur_len),  # Found entries so far
                    str(cur_est_total),  # Total entries
                    str(cur_len),  # Found entries so far
                    str(human_time(cur_est_time)),  # Estimated time
                ))
                time.sleep(COOLDOWN)  # Cooldown so that we are not considered spam
                cur_est_time -= COOLDOWN

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


@app.callback(
    Output("download", "data"),
    Input("dl_all", "n_clicks"),
    State("datatable", "data"),
    State("data_store", "data"),
    prevent_initial_call=True,
)
def download_excel(n_all, data, datastore):
    df = pd.DataFrame(data)
    return dcc.send_data_frame(df.to_excel, "gratte-papier_results.xlsx", sheet_name="results")


if __name__ == "__main__":
    app.run(debug=True)
