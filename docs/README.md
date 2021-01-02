# Salt-RapyutaIO

SaltStack execution modules, state modules, and utilities, for managing a Rapyuta IO project.

## Proxy Minion ##

Because all operations happen in Rapyuta IO, a proxy-minion can be used to manage it.

### Configuration ###

1. On the master configure a pillar entry for your proxy. In this example the proxy minion will have the ID "myproxy":

   ```yaml
   base:
     myproxy:
       - myproxy
   ```

   If you are using the default pillar directory, this will load the file `/srv/pillar/myproxy.sls` for your proxy minion.

1. In the pillar root for your base environment, create the `myproxy.sls` file with the following contents:

    ```yaml
    proxy:
      proxytype: rapyutaio

    rapyutaio:
      #
      # RapyutaIO project and user details
      #
      project_id: "project-xxxxxxxxxxxxxxxxxxxxxxxx"
      username: "user.name@email.com"
      password: "xxxxxxxxxxxxxxxx"

      #
      # RapyutaIO SDB cache
      #
      driver: cache
      bank: rapyutaio
    ```
    
    This tells your proxy minion that it is a "rapyutaio" proxy and uses the credentials under the `rapyutaio` key to connect to Rapyuta IO.
    
1. Make sure the salt-master is running.

1. Start the salt-proxy in debug mode:

    ```bash
    salt-proxy --proxyid=myproxy --log-level=debug
    ```

1. Accept your proxy minion key on the salt-master:

    ```bash
    salt-key --yes --accept myproxy
    ```

1. Test that your proxy minion is working correctly by fetching the rapyutaio grains from the master:

    ```bash
    salt "myproxy" grains.get rapyutaio
    ```

    This should return details about the user account and organisation.

## Available states

### `rapyutaio` ###

*Meta-state (This is a state that includes other states)*.

This installs the rapyutaio package, manages the rapyutaio configuration
file and then starts the associated rapyutaio service.

### `rapyutaio.package` ###

This state will install the rapyutaio package only.

`rapyutaio.config`

This state will configure the rapyutaio service and has a dependency on
`rapyutaio.install` via include list.

`rapyutaio.service`

This state will start the rapyutaio service and has a dependency on
`rapyutaio.config` via include list.

`rapyutaio.clean`

*Meta-state (This is a state that includes other states)*.

this state will undo everything performed in the `rapyutaio` meta-state
in reverse order, i.e. stops the service, removes the configuration file
and then uninstalls the package.

`rapyutaio.service.clean`

This state will stop the rapyutaio service and disable it at boot time.

`rapyutaio.config.clean`

This state will remove the configuration of the rapyutaio service and
has a dependency on `rapyutaio.service.clean` via include list.

`rapyutaio.package.clean`

This state will remove the rapyutaio package and has a depency on
`rapyutaio.config.clean` via include list.