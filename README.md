[![FINOS - Incubating](https://cdn.jsdelivr.net/gh/finos/contrib-toolbox@master/images/badge-incubating.svg)](https://finosfoundation.atlassian.net/wiki/display/FINOS/Incubating)

# FINOS Legend Studio Operator

## Description

The Legend Operators package the core [FINOS Legend](https://legend.finos.org)
components for quick and easy deployment of a Legend stack.

This repository contains a [Juju](https://juju.is/) Charm for
deploying the Studio, the model-centric metadata server for Legend.

The full Legend solution can be installed with the dedicated
[Legend bundle](https://charmhub.io/finos-legend-bundle).


## Usage

The Studio Operator can be deployed by running:

```sh
$ juju deploy finos-legend-studio-k8s --channel=edge
```


## Relations

The standalone Studio will initially be blocked, and will require being later
related to the [Legend Database Operator](https://github.com/canonical/finos-legend-db-operator),
as well as the [Legend GitLab Integrator](https://github.com/canonical/finos-legend-gitlab-integrator).

```sh
$ juju deploy finos-legend-db-k8s finos-legend-gitlab-integrator-k8s
$ juju relate finos-legend-studio-k8s finos-legend-db-k8s
$ juju relate finos-legend-studio-k8s finos-legend-gitlab-integrator-k8s
# If relating to Legend components:
$ juju relate finos-legend-studio-k8s finos-legend-sdlc-k8s
$ juju relate finos-legend-studio-k8s finos-legend-engine-k8s
```

Once related to the DB/GitLab, the Studio can then be related to the
[SDLC](https://github.com/canonical/finos-legend-sdlc-server-operator) and
[Engine](https://github.com/canonical/finos-legend-engine-server-operator):

```sh
$ juju relate finos-legend-studio-k8s finos-legend-sdlc-k8s
$ juju relate finos-legend-studio-k8s finos-legend-engine-k8s
```

## OCI Images

This charm by default uses the latest version of the
[finos/legend-studio](https://hub.docker.com/r/finos/legend-studio) image.

## Charm releases

This repository is configured to automatically build and publish a new Charm revision after a Pull Request merges. For more information, see [here](docs/CharmPublishing.md).

## Contributing

Visit Legend [Contribution Guide](https://github.com/finos/legend/blob/master/CONTRIBUTING.md) to learn how to contribute to Legend.

## License

Copyright (c) 2021-present, Canonical

Distributed under the [Apache License, Version 2.0](http://www.apache.org/licenses/LICENSE-2.0).

SPDX-License-Identifier: [Apache-2.0](https://spdx.org/licenses/Apache-2.0)
