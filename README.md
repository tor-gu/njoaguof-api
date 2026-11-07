
# njoaguof-api

This is the source code for the NJ Use of Force API deployed at
`api.tor-gu.com/nj/use_of_force/`.

It serves the New Jersey Attorney General’s [Use of
Force](https://www.njoag.gov/force/) data, from October 2020 to the
latest release, cleaned and normalized as in the [njoaguof data package
for R](https://github.com/tor-gu/njoaguof). Field names and values are
the same as in the R package, which documents the dataset in detail.

## Try it out

### OpenAPI/Swagger

There is an OpenAPI/swagger document deployed
[here](https://tor-gu.com/apis/njoaguof.html) that you can play with.

### Endpoints

All paths are under `https://api.tor-gu.com/nj/use_of_force`.

| Path                                                                       | Returns                                                              |
|----------------------------------------------------------------------------|----------------------------------------------------------------------|
| `/incidents`, `/incidents/{form_id}`                                       | Incidents, one row per use of force report                           |
| `/incidents/{form_id}/subjects`, `/subjects`                               | The subjects of incidents                                            |
| `/attributes`, `/attributes/{attribute}`, `/attributes/{attribute}/levels` | Multi-value fields (incident type, force type, subject injuries, …)  |
| `/incidents/{form_id}/attributes/{attribute}`                              | One incident’s values of an attribute                                |
| `/agencies`                                                                | Every reporting agency, with its `agency_id` and number of incidents |
| `/officers/{officer_name_id}`, `/officers/{officer_name_id}/name_variants` | An officer’s incidents, and the spellings of the officer’s name      |
| `/counts/incidents`, `/counts/subjects`                                    | Counts grouped by 1 to 3 dimensions (`by=year,agency_county`, …)     |

The collections take the incident filters `year`, `start_date`,
`end_date`, `agency_id`, `agency`, `agency_county`,
`incident_municipality`, `incident_municipality_county` and
`officer_name_id`, combined with AND.

### Sample code

Each endpoint returns paginated results, with a `"next"` url in the
`"links"` section indicating that there are more results to be
retrieved.

This is illustrated in the python code below, which loads Newark PD’s
2025 incidents into a [pandas
DataFrame](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html).
Every incident carries the reporting agency’s `agency_id`, its
identifier in the [njlea](https://github.com/tor-gu/njlea) registry of
NJ law enforcement agencies. Newark PD is `NJLEA0199`.

``` python
import requests
import pandas as pd

API = "https://api.tor-gu.com/nj/use_of_force"


def load_as_df(url):
    """Retrieve every page of the collection at url and return it as a dataframe"""
    frames = []
    while url:
        resp = requests.get(url)
        resp.raise_for_status()
        reply = resp.json()
        frames.append(pd.DataFrame(reply["data"]))
        # Keep retrieving pages while there is a 'next' link
        url = reply["links"].get("next")
    return pd.concat(frames, ignore_index=True)


newark_2025 = load_as_df(f"{API}/incidents?agency_id=NJLEA0199&year=2025&page_size=1000")
```

| form_id | incident_date_1 | agency_id | agency_name | incident_municipality | subject_count | subject_injured_count |
|--------:|:----------------|:----------|:------------|:----------------------|--------------:|----------------------:|
| 1233069 | 2025-01-01      | NJLEA0199 | Newark PD   | Newark city           |             1 |                     0 |
| 1354329 | 2025-03-01      | NJLEA0199 | Newark PD   | Newark city           |             1 |                     0 |
| 1410263 | 2025-01-01      | NJLEA0199 | Newark PD   | Newark city           |             1 |                     0 |
| 1416084 | 2025-01-04      | NJLEA0199 | Newark PD   | Newark city           |             1 |                     0 |
| 1416093 | 2025-01-04      | NJLEA0199 | Newark PD   | Newark city           |             1 |                     0 |
| 1416103 | 2025-01-04      | NJLEA0199 | Newark PD   | Newark city           |             1 |                     0 |

The `counts` endpoints do the aggregation on the server. Here are the
ten agencies with the most incidents in 2025. `agency_id` is the stable
key for an agency: one agency can report under several names or counties
(Rowan University of NJ appears in both Camden and Gloucester counties),
so `/agencies` can list an `agency_id` more than once. We name each
agency by its most frequent entry.

``` python
counts = load_as_df(f"{API}/counts/incidents?by=agency_id&year=2025&page_size=1000")
agencies = load_as_df(f"{API}/agencies?page_size=1000")

names = (
    agencies.sort_values("incident_count", ascending=False)
    .drop_duplicates("agency_id")[["agency_id", "agency_name", "agency_county"]]
)
top_10 = counts.nlargest(10, "count").merge(names, how="left", on="agency_id")
```

| agency_id | agency_name               | agency_county     | count |
|:----------|:--------------------------|:------------------|------:|
| NJLEA0199 | Newark PD                 | Essex County      |  1099 |
| NJLEA0537 | New Jersey State Police   | NA                |  1063 |
| NJLEA0538 | New Jersey Transit Police | NA                |   772 |
| NJLEA0237 | Jersey City PD            | Hudson County     |   606 |
| NJLEA0132 | Camden PD                 | Camden County     |   517 |
| NJLEA0181 | Vineland PD               | Cumberland County |   414 |
| NJLEA0271 | Trenton PD                | Mercer County     |   337 |
| NJLEA0002 | Atlantic City PD          | Atlantic County   |   312 |
| NJLEA0433 | Paterson PD               | Passaic County    |   293 |
| NJLEA0490 | Elizabeth PD              | Union County      |   287 |

Multi-value fields, like the incident type, are served as attribute
tables that join to incidents on `form_id`. Here are the ten most common
types of Newark PD’s 2025 incidents, and the share of them in which a
subject was injured. (Attributes of the `incident_subject` shape also
carry an `index`. It is the position of the value in the source list,
not a subject index, so don’t join those rows to `/subjects` on it.)

``` python
types = load_as_df(f"{API}/attributes/type?agency_id=NJLEA0199&year=2025&page_size=1000")

by_type = (
    types.merge(newark_2025[["form_id", "subject_injured_count"]], on="form_id")
    .assign(subject_injured=lambda df: df["subject_injured_count"] > 0)
    .groupby("type")
    .agg(incidents=("form_id", "count"), share_subject_injured=("subject_injured", "mean"))
    .nlargest(10, "incidents")
    .reset_index()
)
```

| type                                         | incidents | share_subject_injured |
|:---------------------------------------------|----------:|----------------------:|
| Domestic                                     |       244 |                  0.22 |
| Assisting another officer                    |       171 |                  0.26 |
| Potential Mental Health Incident             |       136 |                  0.09 |
| MV/Traffic Stop                              |       113 |                  0.31 |
| Disturbance (drinking, fighting, disorderly) |        87 |                  0.25 |
| Assault                                      |        85 |                  0.13 |
| Subject with a gun                           |        67 |                  0.28 |
| Distribution of CDS                          |        58 |                  0.21 |
| Pedestrian Stop                              |        52 |                  0.23 |
| Suspicious person                            |        52 |                  0.15 |

`agency_id` also joins to the [NJ Law Enforcement Agencies
API](https://tor-gu.com/apis/njlea.html), which serves the njlea
registry at `api.tor-gu.com/nj/lea/`. Here are the 2025 incidents by the
level of government and function of the reporting agency.

``` python
LEA_API = "https://api.tor-gu.com/nj/lea"

registry = load_as_df(f"{LEA_API}/agencies/2025?page_size=1000")

by_level = (
    counts.merge(registry, how="left", on="agency_id")
    .groupby(["agency_level", "agency_function"])
    .agg(agencies=("agency_id", "count"), incidents=("count", "sum"))
    .sort_values("incidents", ascending=False)
    .reset_index()
)
```

| agency_level | agency_function       | agencies | incidents |
|:-------------|:----------------------|---------:|----------:|
| Municipal    | Police                |      425 |     15439 |
| State        | Police                |        2 |      1092 |
| State        | Authority or transit  |        1 |       772 |
| County       | Sheriff               |       20 |       603 |
| County       | Police                |        2 |       531 |
| State        | College or university |        7 |       273 |
| County       | Prosecutor            |       17 |       153 |
| Bi-state     | Authority or transit  |        3 |       128 |
| State        | Corrections           |        2 |        96 |
| County       | Corrections           |        9 |        31 |
| Private      | College or university |        3 |        17 |
| State        | Park and conservation |        1 |         6 |
| County       | Authority or transit  |        1 |         3 |
| State        | Investigative         |        1 |         1 |

The registry also lists the municipalities each agency polices, so we
can add them to the top ten from above. Incidents are counted by agency
here. An agency can police several municipalities, so to count by
municipality, use the `incident_municipality` field. The registry
doesn’t include New Jersey State Police links yet, so its `NA` below
doesn’t mean that it polices no municipalities.

``` python
served = (
    load_as_df(f"{LEA_API}/agency_municipalities/2025?page_size=1000")
    .groupby("agency_id")["municipality"]
    .agg(", ".join)
    .reset_index(name="municipalities")
)
top_10_served = top_10.merge(
    registry[["agency_id", "agency_level", "agency_function"]], how="left", on="agency_id"
).merge(served, how="left", on="agency_id")
```

| agency_name               | agency_level | agency_function      | municipalities                 | count |
|:--------------------------|:-------------|:---------------------|:-------------------------------|------:|
| Newark PD                 | Municipal    | Police               | Newark city                    |  1099 |
| New Jersey State Police   | State        | Police               | NA                             |  1063 |
| New Jersey Transit Police | State        | Authority or transit | NA                             |   772 |
| Jersey City PD            | Municipal    | Police               | Jersey City city               |   606 |
| Camden PD                 | County       | Police               | Camden city, Woodlynne borough |   517 |
| Vineland PD               | Municipal    | Police               | Vineland city                  |   414 |
| Trenton PD                | Municipal    | Police               | Trenton city                   |   337 |
| Atlantic City PD          | Municipal    | Police               | Atlantic City city             |   312 |
| Paterson PD               | Municipal    | Police               | Paterson city                  |   293 |
| Elizabeth PD              | Municipal    | Police               | Elizabeth city                 |   287 |

## Deploying

This API is implemented as an [AWS
SAM](https://aws.amazon.com/serverless/sam/) application
(`template.yaml`), with four lambdas (incidents, attributes, officers
and counts) behind one API Gateway. There are no tables: each lambda’s
data is built from `data/` and packaged with its code. A deployment has
three parts:

1.  The lambda layer
    [layer_torguapi](https://github.com/tor-gu/layer_torguapi), which
    needs to be deployed separately (version 10 or later).
2.  The data: CSV exports of the tables in
    [njoaguof](https://github.com/tor-gu/njoaguof), committed in
    `data/`, from which `make data` builds each lambda’s `data/`
    directory.
3.  The lambdas and API Gateway, defined in `template.yaml`. The API is
    defined by the OpenAPI document `use-of-force-openapi.yaml`, and
    `make apigateway_spec` writes the copy that API Gateway is given
    (`apigateway-openapi.yaml`, without the examples, which API Gateway
    rejects).

### Data

`data/` holds a gzipped CSV for each njoaguof table, `columns.csv` and
`levels.csv` (the column types and factor levels), and `SOURCE`, which
records the njoaguof release they were exported from. To export a
release (this needs R and the `remotes` package; the release is
installed into a temporary library):

    make export_data REF=v2.3.0

### Data update

1.  `make export_data REF=<new release>`, and review the diff in `data/`
    (`columns.csv` and `levels.csv` should only change with the schema).
2.  `make data unit_test example_test`. The example tests reproduce
    every example reply in `use-of-force-openapi.yaml` from the full
    data, and each failure prints the new reply: copy the changed values
    into the spec. Update the date range at the top of the spec.
3.  `make knit`, to refresh the tables in this README.
4.  Push to `dev`, check the dev API, then merge to `main`.

### Local development

    make venv              # .venv, from requirements-dev.txt
    make unit_test         # on the fixtures in tests/fixtures/
    make data example_test # on the full data
    make knit              # README.Rmd -> README.md

The tests need a copy of the layer’s `torguapi` module in `torguapi/`
(gitignored), which `scripts/fetch_torguapi.sh` downloads.

### Direct deploy

The application can be deployed directly using the SAM CLI:

    make data apigateway_spec
    sam build
    sam deploy --stack-name MyStackName                                                         \
               --capabilities CAPABILITY_IAM                                                    \
               --resolve-s3                                                                     \
               --parameter-overrides                                                            \
                    TorguapiLayerArn=arn:aws:lambda:us-east-1:123456789012:layer:layer_torguapi \
                    TorguapiLayerVersion=10                                                     \
                    ApiRoot=https://api.example.com                                             \
                    DataVersion=$(sed -n 's/^version=//p' data/SOURCE)

Replace the `TorguapiLayerXXX` params with the values derived from the
`layer_torguapi` deployment.

The `ApiRoot` value is used only for generating the values in `"links"`
in the JSON reply. On `api.tor-gu.com`, the relationship between the
publicly facing API URL and the API Gateway endpoints is configured in
[torgu-api-cloudfront](https://github.com/tor-gu/torgu-api-cloudfront).

To deploy a second environment alongside the first, give it a resource
name prefix (I use `dev-`) with the `EnvPrefix` template parameter.

### Using GitHub Actions

The workflow I use to deploy from GitHub is
`.github/workflows/deploy.yml`. A push to `dev` deploys the dev stack,
and a push to `main` deploys prod once the run is approved. Each run
runs the unit and example tests, builds the application, deploys it,
and, when the deploy changed the stack, clears the API’s paths from the
CloudFront cache. Integration tests run against the dev stack.

The workflow reaches AWS through OIDC roles, defined with
[Terraform](https://www.terraform.io/) in `infra/github/`: a read-only
role for the tests and a deploy role per environment. Its settings
(stack names, role ARNs, layer version, CloudFront distribution) are in
`pipeline/env/`.
