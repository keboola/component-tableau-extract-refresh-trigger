# Tableau extract trigger app

Trigger Tableu extract refresh tasks directly from KBC.

### Configuration

- **Username** - REQ Tableau user name. Note that the user must be owner of the dataset or Site admin.
- **Password** - REQ Tableau password
- **Endpoint** - REQ Tableu server API endpoint.
- **Poll mode** - Specify whether the app should wait for all triggered tasks to finish.
- **Tableau datasources** - Names of datasources with extract refresh tasks to trigger.
	 - **name** - [REQ] Data source name as found in Tableau.
	 - **tag** - [OPT] Data source tag as found in Tableau. 
	 - **Tableu server unique LUID** [OPT] Optional unique datasource identifier i.e. xx12-3324-1323, 
	 available via API. This ensures unique identification of the datasource. If specified, the `tag` parameter is ignored. 
	 Each run the LUID of refreshed datasets is outputed in the job log - you may use it to get the LUID by specifying only name/tag.
 
**NOTE:** Each datasource **must have** the required extract refresh set up, e.g. `Full refresh`, otherwise it won't be recognized 
and the trigger will fail.

#### LUID setup

If you don't know the LUID you may use unique combination of the `name` and `tag` parameters to identify the datasource. Once you run the configuration 
for the first time, the appropriate `LUID` will be displayed for each specified data source in the **job log**. Use it to update the `LUID` after first run 
to ensure unique match, since there may be more datasources with the same name and tag potentially in the future but LUID is unique at all times.


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

## Testing

The preset pipeline scripts contain sections allowing pushing testing image into the ECR repository and automatic 
testing in a dedicated project. These sections are by default commented out. 

**Running KBC tests on deploy step, before deployment**

Uncomment following section in the deployment step in `bitbucket-pipelines.yml` file:

```yaml
            # push test image to ECR - uncomment when initialised
            # - export REPOSITORY=`docker run --rm -e KBC_DEVELOPERPORTAL_USERNAME -e KBC_DEVELOPERPORTAL_PASSWORD -e KBC_DEVELOPERPORTAL_URL quay.io/keboola/developer-portal-cli-v2:latest ecr:get-repository $KBC_DEVELOPERPORTAL_VENDOR $KBC_DEVELOPERPORTAL_APP`
            # - docker tag $APP_IMAGE:latest $REPOSITORY:test
            # - eval $(docker run --rm -e KBC_DEVELOPERPORTAL_USERNAME -e KBC_DEVELOPERPORTAL_PASSWORD -e KBC_DEVELOPERPORTAL_URL quay.io/keboola/developer-portal-cli-v2:latest ecr:get-login $KBC_DEVELOPERPORTAL_VENDOR $KBC_DEVELOPERPORTAL_APP)
            # - docker push $REPOSITORY:test
            # - docker run --rm -e KBC_STORAGE_TOKEN quay.io/keboola/syrup-cli:latest run-job $KBC_DEVELOPERPORTAL_APP BASE_KBC_CONFIG test
            # - docker run --rm -e KBC_STORAGE_TOKEN quay.io/keboola/syrup-cli:latest run-job $KBC_DEVELOPERPORTAL_APP KBC_CONFIG_1 test
            - ./scripts/update_dev_portal_properties.sh
            - ./deploy.sh
```

Make sure that you have `KBC_STORAGE_TOKEN` env. variable set, containing appropriate storage token with access 
to your KBC project. Also make sure to create a functional testing configuration and replace the `BASE_KBC_CONFIG` placeholder with its id.

**Pushing testing image for manual KBC tests**

In some cases you may wish to execute a testing version of your component manually prior to publishing. For instance to test various
configurations on it. For that it may be convenient to push the `test` image on every push either to master, or any branch.

To achieve that simply uncomment appropriate sections in `bitbucket-pipelines.yml` file, either in master branch step or in `default` step.

```yaml
            # push test image to ecr - uncomment for testing before deployment
#            - echo 'Pushing test image to repo. [tag=test]'
#            - export REPOSITORY=`docker run --rm -e KBC_DEVELOPERPORTAL_USERNAME -e KBC_DEVELOPERPORTAL_PASSWORD -e KBC_DEVELOPERPORTAL_URL quay.io/keboola/developer-portal-cli-v2:latest ecr:get-repository $KBC_DEVELOPERPORTAL_VENDOR $KBC_DEVELOPERPORTAL_APP`
#            - docker tag $APP_IMAGE:latest $REPOSITORY:test
#            - eval $(docker run --rm -e KBC_DEVELOPERPORTAL_USERNAME -e KBC_DEVELOPERPORTAL_PASSWORD -e KBC_DEVELOPERPORTAL_URL quay.io/keboola/developer-portal-cli-v2:latest ecr:get-login $KBC_DEVELOPERPORTAL_VENDOR $KBC_DEVELOPERPORTAL_APP)
#            - docker push $REPOSITORY:test
```
 
 Once the build is finished, you may run such configuration in any KBC project as many times as you want by using [run-job](https://kebooladocker.docs.apiary.io/#reference/run/create-a-job-with-image/run-job) API call, using the `test` image tag.

# Integration

For information about deployment and integration with KBC, please refer to the [deployment section of developers documentation](https://developers.keboola.com/extend/component/deployment/) 