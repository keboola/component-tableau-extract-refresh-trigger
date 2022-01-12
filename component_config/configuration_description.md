Create a [PAT token](https://help.tableau.com/current/pro/desktop/en-us/useracct.htm#create-and-revoke-personal-access-tokens) to authenticate. 

Specify datasource with extract tasks to be refreshed.

**NOTE**: Only extract with tasks/schedules defined will be refreshed.
Any datasources without extract refresh defined won't be available for the trigger.

### LUID setup

The LUIDs are Tableau server internal unique identificators of datasource objects. It is recommended to use the LUID in 
combination with datasource name to ensure there is no ambiguity in the setup, because in theory, it is possible 
for multiple datasources to have same name and/or tags.

If you don't know the LUID you may use unique combination of the `name` and `tag` parameters first to identify the datasource. Once you run the configuration 
for the first time, the appropriate `LUID` will be displayed for each specified data source in the **job log**. 
Look for message like `INFO - Triggering extract for: "TABLEAU_TRIGGER_TEST" with LUID: "067098d0-d160-4117-977c-b18f1051aec7""` 
in the job log and use the displayed `LUID` to update the configuration after first run.

Additional documentation [available here.](https://bitbucket.org/kds_consulting_team/kds-team.app-tableau-extract-refresh-trigger/src/master/README.md)
