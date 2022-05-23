import logging
import re
import sys
from io import StringIO
import pandas as pd
from cldfviz.text import render
from clldutils import jsonlib
from jinja2 import DictLoader
from pylingdocs.config import DATA_DIR
from pylingdocs.config import TABLE_DIR
from pylingdocs.config import TABLE_MD
from pylingdocs.helpers import _get_relative_file
from pylingdocs.helpers import comma_and_list
from pylingdocs.helpers import decorate_gloss_string
from pylingdocs.helpers import get_md_pattern
from pylingdocs.helpers import html_gloss
from pylingdocs.helpers import sanitize_latex
from pylingdocs.helpers import split_ref
from pylingdocs.models import models


log = logging.getLogger(__name__)

MD_LINK_PATTERN = re.compile(r"\[(?P<label>[^]]*)]\((?P<url>[^)]+)\)")

TABLE_PATTERN = re.compile(
    r"PYLINGDOCS_RAW_TABLE_START(?P<label>[\s\S].*)CONTENT_START(?P<content>[\s\S]*?)PYLINGDOCS_RAW_TABLE_END"  # noqa: E501
)


log.info("Loading templates")
labels = {}
templates = {}
list_templates = {}
envs = {}

for model in models:
    labels[model.shortcut] = model.query_string
    for output_format in model.templates:
        if output_format not in templates:
            templates[output_format] = {}
    for output_format in model.list_templates:
        if output_format not in list_templates:
            list_templates[output_format] = {}

for output_format, env_dict in templates.items():
    for model in models:
        model_output = model.representation(output_format)
        if model_output is not None:
            env_dict[model.cldf_table + "_detail.md"] = model_output

for output_format, env_dict in list_templates.items():
    for model in models:
        model_output = model.representation(output_format, multiple=True)
        if model_output is not None:
            env_dict[model.cldf_table + "_index.md"] = model_output

with open(DATA_DIR / "model_templates" / "latex_util.md", "r", encoding="utf-8") as f:
    latex_util = f.read()

templates["latex"]["latex_util.md"] = latex_util

with open(DATA_DIR / "model_templates" / "html_util.md", "r", encoding="utf-8") as f:
    html_util = f.read()

templates["html"]["html_util.md"] = html_util

for output_format, env_dict in templates.items():
    env_dict.update(list_templates[output_format])
    envs[output_format] = DictLoader(env_dict)


def preprocess_cldfviz(md):
    current = 0
    for m in MD_LINK_PATTERN.finditer(md):
        yield md[current : m.start()]
        current, key, url = get_md_pattern(m)
        if key in labels:
            args = []
            kwargs = {}
            if "?" in url:
                url, arguments = url.split("?")
                for arg in arguments.split("&"):
                    if "=" in arg:
                        k, v = arg.split("=")
                        kwargs[k] = v
                    else:
                        args.append(arg)
            if "," in url:
                kwargs.update({"ids": url})
                yield labels[key](
                    url, visualizer="cldfviz", multiple=True, *args, **kwargs
                )
            else:
                yield labels[key](url, visualizer="cldfviz", *args, **kwargs)
        else:
            yield md[m.start() : m.end()]
    yield md[current:]


def render_markdown(md_str, ds, data_format="cldf", output_format="plain"):
    if data_format == "cldf":
        if output_format != "clld":
            preprocessed = render(
                doc="".join(preprocess_cldfviz(md_str)),
                cldf_dict=ds,
                loader=envs[output_format],
                func_dict={
                    "comma_and_list": comma_and_list,
                    "sanitize_latex": sanitize_latex,
                    "split_ref": split_ref,
                    "decorate_gloss_string": decorate_gloss_string,
                    "html_gloss": html_gloss,
                },
            )
            preprocessed = render(
                doc=preprocessed,
                cldf_dict=ds,
                loader=envs[output_format],
                func_dict={"comma_and_list": comma_and_list},
            )
            if "#cldf" in preprocessed:
                preprocessed = render(
                    doc=preprocessed,
                    cldf_dict=ds,
                    loader=envs[output_format],
                    func_dict={"comma_and_list": comma_and_list},
                )
            if "#cldf" in preprocessed:
                preprocessed = render(
                    doc=preprocessed,
                    cldf_dict=ds,
                    loader=envs[output_format],
                    func_dict={"comma_and_list": comma_and_list},
                )
        else:
            preprocessed = "".join(preprocess_cldfviz(md_str))
        return preprocessed
    log.error(f"Unknown data format {data_format}")
    return ""


def load_tables(md):
    current = 0
    for m in MD_LINK_PATTERN.finditer(md):
        yield md[current : m.start()]
        current, key, url = get_md_pattern(m)
        if key == "table":
            table_path = TABLE_DIR / f"{url}.csv"
            if not table_path.is_file():
                log.error(f"Table file <{table_path}> does not exist.")
                sys.exit(1)
            else:
                with open(table_path, "r", encoding="utf-8") as f:
                    yield "PYLINGDOCS_RAW_TABLE_START" + url + "CONTENT_START" + f.read() + "PYLINGDOCS_RAW_TABLE_END"  # noqa: E501
        else:
            yield md[m.start() : m.end()]
    yield md[current:]


def insert_tables(md, builder, tables):
    current = 0
    for m in TABLE_PATTERN.finditer(md):
        yield md[current : m.start()]
        current = m.end()
        label = m.group("label")
        content = m.group("content")
        df = pd.read_csv(StringIO(content), keep_default_na=False)
        df.columns = [col if "Unnamed: " not in col else "" for col in df.columns]
        if label not in tables:
            log.error(f"Could not find metadata for table {label}.")
            sys.exit(1)
        yield builder.table(df=df, caption=tables[label]["caption"], label=label)
    yield md[current:]


def preprocess(md_str):
    return "".join(load_tables(md_str))


def postprocess(md_str, builder):
    table_md = _get_relative_file(TABLE_DIR, TABLE_MD)
    if table_md.is_file():
        tables = jsonlib.load(table_md)
    else:
        tables = {}
    return "".join(insert_tables(md_str, builder, tables))
