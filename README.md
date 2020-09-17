# Tableau extract trigger app

Component allowing to trigger Tableau extract refresh tasks directly from KBC.

**Table of contents:**  
  
[TOC]

# Configuration

## Tableau credentials

- **Username** - [REQ] Tableau user name. Note that the user must be owner of the dataset or Site admin.
- **Password** - [REQ] Tableau password
- **Endpoint** - [REQ] Tableu server API endpoint.
- **Site ID** - [REQ] Tableu Site ID. Optional - for Tableu online.

## Poll mode

Specify whether the app should wait for all triggered tasks to finish. If set to `Yes` the trigger will wait for all triggered jobs to finish, 
otherwise it will trigger all the jobs and finish successfully right after.

## Tableau datasource specification

The trigger application is executing tasks / schedules that are defined on data sources. Specify a list of data sources 
with extracts to trigger in this section. Note that there must be appropriate tasks/schedules set for all 
these sources otherwise the execution will fail.

Each data source is uniquely defined by the `LUID`, which is only available via API and there's no way to retrieve it 
via the UI. For this reason the data source may be identified by several identifiers.

**Steps to set up the data source:**

1. Define data source name and optionally a tag.
2. Define the refresh task type. If not present create it first in the extract definition in Tableau.
3. After first run, look for the LUID outputted in the job log.
4. Set up LUID parameter to fix the unique identification of the data source.

### Data source name

Name of the datasource with extract refresh tasks to trigger as displayed in the UI (see image below). 
**NOTE** This may not be unique. If there's more sources with the same name found the trigger will fail and list of the available,
sources and its' eventual tags will be displayed in the job log. In such case you will need to add a tag to disambiguate.  

### Data source Tag 

Optional parameter defining a data source tag as found in Tableau. Use this to disambiguate the data source if there's 
more data sources with a same name.

### Tableu server unique LUID

Optional unique datasource identifier i.e. xx12-3324-1323,
available via API. This ensures unique identification of the datasource. If specified, the `tag` parameter is ignored.

#### LUID setup

If you don't know the LUID you may use unique combination of the `name` and `tag` parameters to identify the datasource. Once you run the configuration 
for the first time, the appropriate `LUID` will be displayed for each specified data source in the **job log**. Use it to update the `LUID` after first run 
to ensure unique match, since there may be more datasources with the same name and tag potentially in the future but LUID is unique at all times.


### Refresh type
 
Refresh type of the task that is specified for the data source. If the specified type of the refresh task is not defined, 
the job will fail.



![Tableau extract](docs/imgs/extract.png)

**IMPORTANT NOTE:** Each datasource must have the required extract refresh set up, e.g. Full refresh, otherwise it won't be recognized and the trigger will fail. If more tasks of a same type are present, only one of them will be triggered.




## Development

If required, change local data folder (the `CUSTOM_FOLDER` placeholder) path to your custom path in the docker-compose file:

```yaml
    volumes:
      - ./:/code
      - ./CUSTOM_FOLDER:/data
```

**NOTE**: For generation of the config.json using a friendly GUI form use [this link](http://jeremydorn.com/json-editor/?schema=N4IgLgngDgpiBcID2AjAVjAxmEAacAlmADZyIDCSAdgGYEDmArgE4CGYB1eIzMAjowK8AJggDaIRgGcYzbgGIorKVIDuSZqPwwqwqEgJUc+Ye2VIWmGFO77ixAPoBbJMLgBdfFGZJYzDtYIoNKyQeDQZCBSYMyG9NwcJJEAKqwopKyMAAQhzFlUrE5wXj5+kADymqHwAIwADHUAvviKymoaovCgkLAIUTFxCUSkfanpMJk5MnlKKuqa3DQaTux9s+0LJb6yFVVy8ABMDc0gOnoGRmE9kdGxVPH4iSOIYxnZ0wBuslkAggAKAEksmd9IZjCBvNt/BBKm59gcAKxNLxIezOVxkboRPpURhOFChR7DSJ/VHELIuNzcNxSTCxKAcLiIAE0LIyMBZMBILIAAwAmtYeZyABYwTmxej0b6qAj2LKqVhELJLPKsOUDSWyGDCLJoVBSTncuhUAhSYW4LJIMCi5gymRZJUy9USqWq9Wi3X6rKsXTKwym4VsxiYKwqGiMewQLIS4Uc1g0MCyAB0tlKOxhewQABYEQjtLinOI6rgap4QG4aJliDh4MXkAzOFQbF1TgWHE9AvAJAA5JDcAU2dyNE6mMDmSydrG9RCsZhsCBDJKjNJvLKj8fMUPU6x0ggNpkgAAypo5SFZ66kFk31nlREDMAAHjFWNgDVzxQxXUmsr3EyL2CKWoUtIHIEt6UCQt4BDsGKY5SAA1lIAD0tKisIEY3uyyoaN67rWGKl4TgaVo2nasEeo+WCMIyVC3nKlaytwRAwE4zagCqKw1iA9CxFo4TTsg6BYOCHZ9AAok+bDYNwvACEI2riCABRFAkrAPCAxCCHx1wgGWkE7AQk5KYUmL8TcAz3IuzwgAAImYbJXlY+QmSmJg7vSNF9AAPCgAB8ABK/CCCIXlIX5WR2WODkTs5RTegaSyML6hhZK8EyMK5EJptCsLVPUxyPGpVzYogtyDESS6IJFrDRdenJqZlNK7vuVB9OULVqmu9mEXVY70PF2FJTqKVpZkmX6TlmaHA0yIaVpxUCWVlkVdZaXvLIXx5ElBACGKh4AKoAjZlqstaYoXo5YoABTKNGMDePhRjalkHzQb8gIAJTbrSHmNm1HXkttu1dXBl0Om4RgEHQ3wEEmMDfg+D41AcAC0ADMaMHFmKM1JjaMWqwHyKsQK5iq9NX/AC37JMKprAk2LA3kDjBigQEMcHQmDsI2J2ASDG5WN+LJsrAmBQ4ZwgWmdWQAOR9TLWRKGwRSJnkdMMFQGjauN2W7HCCBozNJw6S2Oh4opgU0LwZoSc+2CpAh3AAlQdIsToYC21JYAO/Bun4L4NFsa2eLtsSzYSAAYhGxBOy7vBFEYaq6cbJX9Hc6miYglvW4GOluT9e6eYgnsvhyvBW9YufYm5lYRlxUf2KmUJ69UWZG8OHdAAA=&value=N4IgrgzgpgTiBcIQBoQGIAOBDCEDuA9jACYJKpQB2xGBAlpQC5koi0A27A+gLYHFQEABlTEsjHATAwAxlAgIA2qEpYegxDlKoJAczJbW7MHVKJWjAJ4YNIAEpQAZjHkALAKIAPRjCwzGACo4ANYgAL4AumFAAA==&theme=bootstrap2&iconlib=fontawesome4&object_layout=normal&show_errors=interaction)

Clone this repository, init the workspace and run the component with following command:

```
git clone repo_path my-new-component
cd my-new-component
docker-compose build
docker-compose run --rm dev
```

Run the test suite and lint check using this command:

```
docker-compose run --rm test
```

# Integration

For information about deployment and integration with KBC, please refer to the [deployment section of developers documentation](https://developers.keboola.com/extend/component/deployment/) 