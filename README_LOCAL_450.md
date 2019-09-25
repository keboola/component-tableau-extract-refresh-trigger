# Tableau extract trigger app

Trigger Tableu extract refresh tasks directly from KBC.

### Configuration

- **Username** - REQ Tableau user name. Note that the user must be owner of the dataset or Site admin.
- **Password** - REQ Tableau password
- **Endpoint** - REQ Tableu server API endpoint.
- **Poll mode** - Specify whether the app should wait for all triggered tasks to finish.
- **Tableau datasources** - Names of datasources with extract refresh tasks to trigger. 




**NOTE:** Each datasource **must have** the required extract refresh set up, e.g. `Full refresh`, otherwise it won't be recognized 
and the trigger will fail.

## Development

If required, change local data folder (the `CUSTOM_FOLDER` placeholder) path to your custom path in the docker-compose file:

```yaml
    volumes:
      - ./:/code
      - ./CUSTOM_FOLDER:/data
```

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